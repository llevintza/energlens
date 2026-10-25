"""The Postgres job queue: enqueue, claim, finish, reap. See ADR-0022.

Everything here takes a session and commits nothing except where a function
says it does, with one exception that is the point of the module: ``claim_job``
must commit on its own, because the row lock it takes is what keeps a second
consumer off the same job, and holding that lock for the 20–60 seconds a
handler runs would serialise every other queue operation behind it.

Sized for the real load — 1–3 bills at a time, one consumer — and written so a
second consumer would still be safe (``FOR UPDATE SKIP LOCKED``), not so that
one would be fast.
"""

import uuid
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bill_document import BillDocument
from app.models.bill_job import (
    JOB_ACTIVE_STATUSES,
    JOB_CLAIMED,
    JOB_DEAD,
    JOB_FAILED,
    JOB_QUEUED,
    JOB_RUNNING,
    JOB_STATUSES,
    JOB_SUCCEEDED,
    BillJob,
)

# A worker heartbeats every 10 s while a job runs, so two minutes is twelve
# missed beats — not a slow handler, a dead process.
STALE_AFTER = timedelta(minutes=2)

# Long enough to be a useful error, short enough that a traceback-sized message
# from a third-party client never bloats the row.
_MAX_ERROR_CHARS = 4000


def backoff(attempts: int) -> timedelta:
    """``2^attempts`` minutes: 2, 4, 8 … after the first, second, third try."""
    return timedelta(minutes=2**attempts)


async def enqueue_job(
    session: AsyncSession, document: BillDocument, kind: str
) -> tuple[BillJob, bool]:
    """Queue ``kind`` for ``document``, or return the job already in flight.

    Returns ``(job, created)``. At most one *active* job may exist per
    (document, kind) — the reasoning is on BillJob. The check-then-insert is
    serialised by locking the document row, so two concurrent uploads of the
    same file cannot both see "none active" and both insert. Commits.
    """
    await session.execute(
        select(BillDocument.id).where(BillDocument.id == document.id).with_for_update()
    )
    existing = await session.scalar(
        select(BillJob).where(
            BillJob.document_id == document.id,
            BillJob.kind == kind,
            BillJob.status.in_(JOB_ACTIVE_STATUSES),
        )
    )
    if existing is not None:
        await session.commit()
        return existing, False
    job = BillJob(place_id=document.place_id, document_id=document.id, kind=kind)
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job, True


async def claim_job(session: AsyncSession) -> BillJob | None:
    """Claim the oldest runnable job, or return None. Commits.

    One statement, not a SELECT then an UPDATE: between those two a second
    consumer could read the same row. ``SKIP LOCKED`` makes a concurrent claimer
    pass over a row this one has locked instead of waiting for it, so each gets
    a different job — tests/test_jobs.py claims from two sessions to prove it.
    """
    job = await session.scalar(claim_statement())
    await session.commit()
    return job


def claim_statement():
    """The claiming UPDATE on its own, so a test can hold its lock open."""
    claimable = (
        select(BillJob.id)
        .where(BillJob.status == JOB_QUEUED, BillJob.run_after <= func.now())
        .order_by(BillJob.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
        .scalar_subquery()
    )
    return (
        update(BillJob)
        .where(BillJob.id == claimable)
        .values(
            status=JOB_CLAIMED,
            claimed_at=func.now(),
            heartbeat_at=func.now(),
            attempts=BillJob.attempts + 1,
        )
        .returning(BillJob)
        .execution_options(synchronize_session=False)
    )


async def mark_running(session: AsyncSession, job_id: uuid.UUID) -> None:
    await session.execute(
        update(BillJob)
        .where(BillJob.id == job_id, BillJob.status == JOB_CLAIMED)
        .values(status=JOB_RUNNING, heartbeat_at=func.now())
    )
    await session.commit()


async def heartbeat(session: AsyncSession, job_id: uuid.UUID) -> None:
    await session.execute(
        update(BillJob)
        .where(BillJob.id == job_id, BillJob.status.in_((JOB_CLAIMED, JOB_RUNNING)))
        .values(heartbeat_at=func.now())
    )
    await session.commit()


# The finishing writes are all guarded on the job still being ours (claimed or
# running). If the reaper has already taken it back, a late finish from the
# process it gave up on must not overwrite whatever has happened since.


async def mark_succeeded(session: AsyncSession, job_id: uuid.UUID) -> None:
    await session.execute(
        update(BillJob)
        .where(BillJob.id == job_id, BillJob.status.in_((JOB_CLAIMED, JOB_RUNNING)))
        .values(status=JOB_SUCCEEDED, last_error=None)
    )
    await session.commit()


async def mark_failed(session: AsyncSession, job_id: uuid.UUID, error: str) -> None:
    """The handler ran and reached a verdict: the result is bad. No retry."""
    await session.execute(
        update(BillJob)
        .where(BillJob.id == job_id, BillJob.status.in_((JOB_CLAIMED, JOB_RUNNING)))
        .values(status=JOB_FAILED, last_error=error[:_MAX_ERROR_CHARS])
    )
    await session.commit()


async def retry_or_bury(session: AsyncSession, job: BillJob, error: str) -> str:
    """The handler raised before reaching a verdict. Back off, or give up.

    Requeues with ``run_after = now() + 2^attempts`` minutes while attempts
    remain; at ``attempts >= max_attempts`` the job is ``dead`` with the error
    kept. Returns the new status.
    """
    status = JOB_DEAD if job.attempts >= job.max_attempts else JOB_QUEUED
    values: dict = {"status": status, "last_error": error[:_MAX_ERROR_CHARS]}
    if status == JOB_QUEUED:
        values["run_after"] = func.now() + backoff(job.attempts)
    await session.execute(
        update(BillJob)
        .where(BillJob.id == job.id, BillJob.status.in_((JOB_CLAIMED, JOB_RUNNING)))
        .values(**values)
    )
    await session.commit()
    return status


async def reap_stale_jobs(
    session: AsyncSession, stale_after: timedelta = STALE_AFTER
) -> dict[str, int]:
    """Rescue jobs whose worker stopped heartbeating. Commits.

    This is what makes a Render spin-down survivable: the process dies mid-job,
    the row stays ``claimed``/``running``, and the next boot — or the next sweep
    from .github/workflows/agent-sweep.yml — puts it back in the queue.

    Requeued immediately rather than with backoff: the job did not fail, its
    process went away. The attempt it was claimed with is still spent, though,
    so a job that kills its worker every time ends ``dead`` instead of looping.
    Returns ``{"requeued": n, "dead": m}``.
    """
    stale = BillJob.status.in_((JOB_CLAIMED, JOB_RUNNING)) & (
        BillJob.heartbeat_at < func.now() - stale_after
    )
    error = "worker stopped heartbeating; requeued by the reaper"
    dead = await session.scalars(
        update(BillJob)
        .where(stale, BillJob.attempts >= BillJob.max_attempts)
        .values(status=JOB_DEAD, last_error=error)
        .returning(BillJob.id)
        .execution_options(synchronize_session=False)
    )
    dead_count = len(dead.all())
    requeued = await session.scalars(
        update(BillJob)
        .where(stale)
        .values(status=JOB_QUEUED, run_after=func.now(), last_error=error)
        .returning(BillJob.id)
        .execution_options(synchronize_session=False)
    )
    requeued_count = len(requeued.all())
    await session.commit()
    return {"requeued": requeued_count, "dead": dead_count}


async def count_by_status(session: AsyncSession) -> dict[str, int]:
    """Every status, zeros included, so a caller can read a key without a get."""
    rows = await session.execute(
        select(BillJob.status, func.count()).group_by(BillJob.status)
    )
    counts = dict.fromkeys(JOB_STATUSES, 0)
    counts.update({status: n for status, n in rows.all()})
    return counts
