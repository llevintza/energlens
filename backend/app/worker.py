"""The in-process job worker: one asyncio task inside the API. See ADR-0022.

Started from the FastAPI lifespan in app/main.py when ``settings.worker_enabled``
is true, with concurrency 1. It **polls** every 5 seconds, deliberately:
``LISTEN`` needs a connection held out of SQLAlchemy's pool for the listener's
whole lifetime, which fights pool sizing, Neon's idle timeouts and Render's
spin-down — all to shave at most 5 s off a 20–60 s job. A ``NOTIFY`` on insert
is fine later as a latency optimisation *on top of* polling; polling must stay
the mechanism that guarantees a job runs. Read ADR-0022 before changing this.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.bill_job import JOB_KIND_EXTRACT, BillJob
from app.services import jobs

logger = logging.getLogger(__name__)

POLL_INTERVAL = 5.0
HEARTBEAT_INTERVAL = 10.0
REAP_INTERVAL = 60.0

Handler = Callable[[BillJob], Awaitable[None]]


class JobFailed(Exception):
    """Raised by a handler that ran and reached a verdict: the result is bad.

    Anything else a handler raises means it never got that far, and the job is
    retried with backoff. The distinction is ``failed`` versus ``dead``.
    """


async def _noop(job: BillJob) -> None:
    """Placeholder until #59 registers the real extraction handler.

    Shipping the queue without it keeps the queue testable without an API key.
    """
    logger.info("job %s (%s): no-op handler", job.id, job.kind)


HANDLERS: dict[str, Handler] = {JOB_KIND_EXTRACT: _noop}


class Worker:
    def __init__(
        self,
        session_maker: async_sessionmaker[AsyncSession],
        handlers: dict[str, Handler] | None = None,
        *,
        poll_interval: float = POLL_INTERVAL,
        heartbeat_interval: float = HEARTBEAT_INTERVAL,
        reap_interval: float = REAP_INTERVAL,
    ) -> None:
        self.session_maker = session_maker
        self.handlers = HANDLERS if handlers is None else handlers
        self.poll_interval = poll_interval
        self.heartbeat_interval = heartbeat_interval
        self.reap_interval = reap_interval

    async def run(self) -> None:
        """Reap on boot, then claim-and-run until cancelled."""
        loop = asyncio.get_running_loop()
        last_reap = None
        while True:
            try:
                if last_reap is None or loop.time() - last_reap >= self.reap_interval:
                    await self.reap()
                    last_reap = loop.time()
                if await self.run_once():
                    continue
            # A suspended Neon or a network blip must not kill the task for the
            # rest of the process's life — log it and try again next poll.
            # CancelledError is a BaseException, so shutdown still gets through.
            except Exception:
                logger.exception("job worker: poll failed")
            await asyncio.sleep(self.poll_interval)

    async def reap(self) -> dict[str, int]:
        async with self.session_maker() as session:
            result = await jobs.reap_stale_jobs(session)
        if result["requeued"] or result["dead"]:
            logger.warning("job worker: reaper %s", result)
        return result

    async def run_once(self) -> bool:
        """Claim one job and run it to a verdict. False when nothing is queued."""
        async with self.session_maker() as session:
            job = await jobs.claim_job(session)
        if job is None:
            return False

        beat = asyncio.create_task(self._heartbeat(job))
        try:
            async with self.session_maker() as session:
                await jobs.mark_running(session, job)
            handler = self.handlers.get(job.kind)
            if handler is None:
                raise LookupError(f"no handler registered for job kind {job.kind!r}")
            await handler(job)
        except JobFailed as exc:
            async with self.session_maker() as session:
                await jobs.mark_failed(session, job, str(exc) or type(exc).__name__)
            logger.warning("job %s failed: %s", job.id, exc)
        except Exception as exc:
            async with self.session_maker() as session:
                status = await jobs.retry_or_bury(session, job, f"{type(exc).__name__}: {exc}")
            logger.exception("job %s raised; now %s", job.id, status)
        else:
            async with self.session_maker() as session:
                await jobs.mark_succeeded(session, job)
        finally:
            beat.cancel()
            with suppress(asyncio.CancelledError):
                await beat
        return True

    async def _heartbeat(self, job: BillJob) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_interval)
            try:
                async with self.session_maker() as session:
                    await jobs.heartbeat(session, job)
            except Exception:
                # A missed beat is survivable; twelve of them is what the reaper
                # is for. Never let it take the handler down with it.
                logger.exception("job %s: heartbeat failed", job.id)


def start_worker(session_maker: async_sessionmaker[AsyncSession]) -> asyncio.Task:
    return asyncio.create_task(Worker(session_maker).run(), name="job-worker")


async def stop_worker(task: asyncio.Task) -> None:
    """Cancel and wait, so shutdown never logs "Task was destroyed but it is
    pending". A job interrupted here stays claimed and the reaper rescues it."""
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
