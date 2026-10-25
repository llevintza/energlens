"""The Postgres job queue, the in-process worker, and the sweep route (ADR-0022).

The worker is never started by the app under test — settings.worker_enabled is
pinned off in conftest.py — so these drive Worker and app/services/jobs.py
directly, against the real test database. A fake queue would prove nothing
about the one property that matters most here, SKIP LOCKED.
"""

import asyncio
import uuid
from datetime import timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.main as main_module
from app.config import Settings
from app.db import get_async_session
from app.main import app, lifespan
from app.models import BillDocument, BillJob
from app.models.bill_job import JOB_KIND_EXTRACT
from app.routers.internal import build_internal_router
from app.services import jobs
from app.worker import JobFailed, Worker, stop_worker
from tests.conftest import make_pdf, pdf_upload

SWEEP = "/internal/jobs/sweep"
TOKEN = "test-internal-token"


@pytest.fixture
def maker(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
async def upload(client, auth_headers, place, maker):
    """Upload a distinct PDF and return its BillDocument row."""
    count = 0

    async def _upload() -> BillDocument:
        nonlocal count
        count += 1
        r = await client.post(
            f"/places/{place['id']}/bill-documents",
            files=pdf_upload(make_pdf(marker=f"job-{count}")),
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
        async with maker() as session:
            return await session.get(BillDocument, uuid.UUID(r.json()["id"]))

    return _upload


@pytest.fixture
def enqueue(maker):
    async def _enqueue(document: BillDocument) -> BillJob:
        async with maker() as session:
            job, created = await jobs.enqueue_job(session, document, JOB_KIND_EXTRACT)
        assert created
        return job

    return _enqueue


async def fetch(maker, job_id) -> BillJob:
    async with maker() as session:
        return await session.get(BillJob, job_id, populate_existing=True)


async def make_stale(maker, job_id) -> None:
    """What a process killed mid-job leaves behind: no heartbeat for 3 minutes."""
    async with maker() as session:
        await session.execute(
            update(BillJob)
            .where(BillJob.id == job_id)
            .values(heartbeat_at=func.now() - timedelta(minutes=3))
        )
        await session.commit()


async def make_due(maker, job_id) -> None:
    """Skip the backoff wait, so a test can retry without sleeping minutes."""
    async with maker() as session:
        await session.execute(
            update(BillJob).where(BillJob.id == job_id).values(run_after=func.now())
        )
        await session.commit()


def worker(maker, **handlers) -> Worker:
    async def ok(job):
        return None

    return Worker(maker, handlers or {JOB_KIND_EXTRACT: ok}, poll_interval=0.05)


class TestEnqueue:
    async def test_one_active_job_per_document_and_kind(self, upload, maker):
        document = await upload()
        async with maker() as session:
            first, created = await jobs.enqueue_job(session, document, JOB_KIND_EXTRACT)
            again, created_again = await jobs.enqueue_job(
                session, document, JOB_KIND_EXTRACT
            )
        assert created and not created_again
        assert again.id == first.id
        assert first.status == "queued" and first.attempts == 0

    async def test_a_finished_document_can_be_queued_again(self, upload, enqueue, maker):
        """Re-runnable after a prompt change — why this is not a UniqueConstraint."""
        document = await upload()
        first = await enqueue(document)
        assert await worker(maker).run_once()
        assert (await fetch(maker, first.id)).status == "succeeded"
        second = await enqueue(document)
        assert second.id != first.id

    async def test_concurrent_enqueues_create_one_job(self, upload, maker):
        document = await upload()

        async def one():
            async with maker() as session:
                return await jobs.enqueue_job(session, document, JOB_KIND_EXTRACT)

        results = await asyncio.gather(*(one() for _ in range(5)))
        assert len({job.id for job, _ in results}) == 1
        assert sum(created for _, created in results) == 1


class TestClaim:
    async def test_two_concurrent_claimers_never_get_the_same_job(
        self, upload, enqueue, maker
    ):
        """The reason the claim is one UPDATE … FOR UPDATE SKIP LOCKED.

        A holds its claim open — row locked, transaction uncommitted — while B
        claims. Without SKIP LOCKED, B would block on A's row (the wait_for
        turns that into a failure) and then, once A committed, re-check it and
        find nothing; with a SELECT-then-UPDATE, B could take A's row outright.
        """
        one = await enqueue(await upload())
        two = await enqueue(await upload())
        async with maker() as a, maker() as b:
            held = await a.scalar(jobs.claim_statement())
            other = await asyncio.wait_for(jobs.claim_job(b), timeout=5)
            await a.commit()
        assert held is not None and other is not None
        assert {held.id, other.id} == {one.id, two.id}

    async def test_a_locked_last_job_is_skipped_not_waited_on(
        self, upload, enqueue, maker
    ):
        await enqueue(await upload())
        async with maker() as a, maker() as b:
            held = await a.scalar(jobs.claim_statement())
            assert await asyncio.wait_for(jobs.claim_job(b), timeout=5) is None
            await a.commit()
        assert held is not None

    async def test_many_parallel_claimers_each_get_a_different_job(
        self, upload, enqueue, maker
    ):
        queued = {(await enqueue(await upload())).id for _ in range(4)}

        async def claim():
            async with maker() as session:
                return await jobs.claim_job(session)

        claimed = await asyncio.gather(*(claim() for _ in range(6)))
        ids = [job.id for job in claimed if job is not None]
        assert sorted(ids) == sorted(queued)

    async def test_claim_marks_the_row(self, upload, enqueue, maker):
        job = await enqueue(await upload())
        async with maker() as session:
            claimed = await jobs.claim_job(session)
        assert claimed.id == job.id
        assert claimed.status == "claimed"
        assert claimed.attempts == 1
        assert claimed.claimed_at is not None and claimed.heartbeat_at is not None

    async def test_oldest_first(self, upload, enqueue, maker):
        first = await enqueue(await upload())
        await enqueue(await upload())
        async with maker() as session:
            assert (await jobs.claim_job(session)).id == first.id


class TestReaper:
    async def test_a_job_whose_worker_died_is_requeued_and_then_succeeds(
        self, upload, enqueue, maker
    ):
        job = await enqueue(await upload())
        async with maker() as session:
            claimed = await jobs.claim_job(session)
            await jobs.mark_running(session, claimed)
        await make_stale(maker, job.id)

        assert await worker(maker).reap() == {"requeued": 1, "dead": 0}
        assert (await fetch(maker, job.id)).status == "queued"

        assert await worker(maker).run_once()
        done = await fetch(maker, job.id)
        assert done.status == "succeeded"
        assert done.attempts == 2

    async def test_a_late_write_from_the_reaped_claim_does_not_touch_the_new_one(
        self, upload, enqueue, maker
    ):
        """The old process wakes up after the reaper gave its job to someone else."""
        job = await enqueue(await upload())
        async with maker() as session:
            stale_claim = await jobs.claim_job(session)
        await make_stale(maker, job.id)
        assert await worker(maker).reap() == {"requeued": 1, "dead": 0}
        async with maker() as session:
            new_claim = await jobs.claim_job(session)
            await jobs.mark_running(session, new_claim)
        assert new_claim.attempts == stale_claim.attempts + 1
        before = await fetch(maker, job.id)

        async with maker() as session:
            await jobs.heartbeat(session, stale_claim)
            await jobs.mark_succeeded(session, stale_claim)
            await jobs.mark_failed(session, stale_claim, "late verdict")
            await jobs.retry_or_bury(session, stale_claim, "late error")

        after = await fetch(maker, job.id)
        assert after.status == "running"
        assert after.attempts == new_claim.attempts
        assert after.heartbeat_at == before.heartbeat_at
        assert after.last_error == before.last_error

        async with maker() as session:
            await jobs.mark_succeeded(session, new_claim)
        assert (await fetch(maker, job.id)).status == "succeeded"

    async def test_a_live_job_is_left_alone(self, upload, enqueue, maker):
        job = await enqueue(await upload())
        async with maker() as session:
            await jobs.claim_job(session)
        assert await worker(maker).reap() == {"requeued": 0, "dead": 0}
        assert (await fetch(maker, job.id)).status == "claimed"

    async def test_a_job_that_keeps_killing_its_worker_ends_dead(
        self, upload, enqueue, maker
    ):
        job = await enqueue(await upload())
        for _ in range(3):
            async with maker() as session:
                assert (await jobs.claim_job(session)).id == job.id
            await make_stale(maker, job.id)
            await worker(maker).reap()
        dead = await fetch(maker, job.id)
        assert dead.status == "dead"
        assert dead.attempts == 3
        assert "heartbeat" in dead.last_error


class TestRetries:
    async def test_backoff_delays_the_retry_and_max_attempts_buries_it(
        self, upload, enqueue, maker
    ):
        async def boom(job):
            raise RuntimeError("upstream said no")

        w = worker(maker, **{JOB_KIND_EXTRACT: boom})
        job = await enqueue(await upload())

        assert await w.run_once()
        retried = await fetch(maker, job.id)
        assert retried.status == "queued"
        assert retried.attempts == 1
        assert "upstream said no" in retried.last_error
        async with maker() as session:
            delay = await session.scalar(
                select(BillJob.run_after - func.now()).where(BillJob.id == job.id)
            )
        # 2^1 minutes, give or take the test's own runtime.
        assert timedelta(minutes=1, seconds=50) < delay <= timedelta(minutes=2)
        # Not claimable until then.
        assert not await w.run_once()

        await make_due(maker, job.id)
        assert await w.run_once()
        assert (await fetch(maker, job.id)).attempts == 2

        await make_due(maker, job.id)
        assert await w.run_once()
        dead = await fetch(maker, job.id)
        assert dead.status == "dead"
        assert dead.attempts == 3
        assert "RuntimeError: upstream said no" == dead.last_error

    async def test_a_verdict_is_failed_not_retried(self, upload, enqueue, maker):
        async def bad_result(job):
            raise JobFailed("totals do not add up")

        job = await enqueue(await upload())
        assert await worker(maker, **{JOB_KIND_EXTRACT: bad_result}).run_once()
        failed = await fetch(maker, job.id)
        assert failed.status == "failed"
        assert failed.attempts == 1
        assert failed.last_error == "totals do not add up"

    async def test_an_unknown_kind_is_retried_not_dropped(self, upload, enqueue, maker):
        job = await enqueue(await upload())
        assert await worker(maker, other=lambda job: None).run_once()
        retried = await fetch(maker, job.id)
        assert retried.status == "queued"
        assert "no handler" in retried.last_error


class TestWorker:
    async def test_the_shipped_handler_is_a_no_op_that_succeeds(
        self, upload, enqueue, maker
    ):
        """#59 replaces it; until then a queued extract must not pile up."""
        job = await enqueue(await upload())
        assert await Worker(maker).run_once()
        assert (await fetch(maker, job.id)).status == "succeeded"

    async def test_heartbeats_while_the_handler_runs(self, upload, enqueue, maker):
        seen = {}

        async def slow(job):
            claimed = await fetch(maker, job.id)
            seen["status"] = claimed.status
            await asyncio.sleep(0.5)

        w = Worker(maker, {JOB_KIND_EXTRACT: slow}, heartbeat_interval=0.1)
        job = await enqueue(await upload())
        assert await w.run_once()
        done = await fetch(maker, job.id)
        assert seen["status"] == "running"
        assert done.heartbeat_at > done.claimed_at

    async def test_run_survives_a_database_error_and_keeps_polling(
        self, upload, enqueue, maker, monkeypatch
    ):
        calls = 0
        real = jobs.claim_job

        async def flaky(session):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise ConnectionError("neon is asleep")
            return await real(session)

        monkeypatch.setattr(jobs, "claim_job", flaky)
        job = await enqueue(await upload())
        task = asyncio.create_task(worker(maker).run())
        try:
            for _ in range(100):
                if (await fetch(maker, job.id)).status == "succeeded":
                    break
                await asyncio.sleep(0.05)
        finally:
            await stop_worker(task)
        assert (await fetch(maker, job.id)).status == "succeeded"

    async def test_cancels_within_a_second_mid_job(self, upload, enqueue, maker):
        started = asyncio.Event()

        async def forever(job):
            started.set()
            await asyncio.sleep(3600)

        job = await enqueue(await upload())
        task = asyncio.create_task(worker(maker, **{JOB_KIND_EXTRACT: forever}).run())
        await asyncio.wait_for(started.wait(), timeout=5)

        loop = asyncio.get_running_loop()
        began = loop.time()
        await stop_worker(task)
        assert loop.time() - began < 1
        assert task.done()
        # Left for the reaper, which is the whole recovery story.
        assert (await fetch(maker, job.id)).status == "running"


class TestLifespan:
    def test_worker_is_off_by_default(self):
        assert Settings.model_fields["worker_enabled"].default is False

    async def test_lifespan_does_not_start_it_when_disabled(self, monkeypatch):
        started = []
        monkeypatch.setattr(main_module, "start_worker", lambda m: started.append(m))
        monkeypatch.setattr(main_module.settings, "worker_enabled", False)
        async with lifespan(app):
            pass
        assert started == []

    async def test_lifespan_starts_it_and_stops_it_within_a_second(
        self, maker, monkeypatch
    ):
        tasks = []
        real_start = main_module.start_worker

        def spy(session_maker):
            task = real_start(session_maker)
            tasks.append(task)
            return task

        monkeypatch.setattr(main_module, "start_worker", spy)
        monkeypatch.setattr(main_module, "async_session_maker", maker)
        monkeypatch.setattr(main_module.settings, "worker_enabled", True)

        loop = asyncio.get_running_loop()
        async with lifespan(app):
            await asyncio.sleep(0.2)  # into its first poll
            assert len(tasks) == 1 and not tasks[0].done()
            began = loop.time()
        assert loop.time() - began < 1
        assert tasks[0].done()


class TestSweepRoute:
    def test_absent_when_no_token_is_configured(self):
        assert not any(getattr(r, "path", "").startswith("/internal") for r in app.routes)

    def test_refuses_to_build_with_a_blank_token(self):
        with pytest.raises(ValueError):
            build_internal_router("")

    @pytest.fixture
    async def internal(self, maker):
        """A bare app with only the internal router — the real app has no token."""
        api = FastAPI()
        api.include_router(build_internal_router(TOKEN))

        async def override():
            async with maker() as session:
                yield session

        api.dependency_overrides[get_async_session] = override
        async with AsyncClient(transport=ASGITransport(app=api), base_url="http://t") as c:
            yield c

    async def test_401_without_the_token(self, internal):
        assert (await internal.post(SWEEP)).status_code == 401

    async def test_401_with_the_wrong_token(self, internal):
        r = await internal.post(SWEEP, headers={"X-Internal-Token": TOKEN + "x"})
        assert r.status_code == 401

    async def test_reaps_and_reports_counts(self, internal, upload, enqueue, maker):
        stale = await enqueue(await upload())
        await enqueue(await upload())
        async with maker() as session:
            assert (await jobs.claim_job(session)).id == stale.id
        await make_stale(maker, stale.id)

        r = await internal.post(SWEEP, headers={"X-Internal-Token": TOKEN})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["reaped"] == {"requeued": 1, "dead": 0}
        assert body["counts"]["queued"] == 2
        assert body["counts"]["claimed"] == 0
        assert set(body["counts"]) == {
            "queued", "claimed", "running", "succeeded", "failed", "dead", "cancelled",
        }
