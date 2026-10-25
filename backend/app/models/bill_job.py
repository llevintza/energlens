import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# The lifecycle, in order. ``claimed`` is the instant between the claiming
# UPDATE committing and the handler starting; ``running`` is the handler.
#
# ``failed`` and ``dead`` are different verdicts and the dashboards in #51 treat
# them differently: ``failed`` is a job that ran and produced a bad result,
# ``dead`` is one that never got a verdict — it ran out of attempts.
JOB_QUEUED = "queued"
JOB_CLAIMED = "claimed"
JOB_RUNNING = "running"
JOB_SUCCEEDED = "succeeded"
JOB_FAILED = "failed"
JOB_DEAD = "dead"
JOB_CANCELLED = "cancelled"

JOB_STATUSES = (
    JOB_QUEUED,
    JOB_CLAIMED,
    JOB_RUNNING,
    JOB_SUCCEEDED,
    JOB_FAILED,
    JOB_DEAD,
    JOB_CANCELLED,
)
JOB_ACTIVE_STATUSES = (JOB_QUEUED, JOB_CLAIMED, JOB_RUNNING)
JOB_TERMINAL_STATUSES = (JOB_SUCCEEDED, JOB_FAILED, JOB_DEAD, JOB_CANCELLED)

# The only kind today. The column exists so the next kind is not a new table.
JOB_KIND_EXTRACT = "extract"


class BillJob(Base):
    """A unit of background work about one bill document, queued in Postgres.

    The queue lives here rather than in Redis or a second service because the
    API runs on one free Render web service — see ADR-0023. Durability comes
    from this row, not from the process: a worker that dies mid-job leaves the
    row ``claimed``/``running`` with a stale ``heartbeat_at``, and the reaper
    in app/services/jobs.py puts it back in the queue.

    **At most one active job per (document_id, kind).** That is a uniqueness
    rule over ``status IN (queued, claimed, running)`` only — the same document
    must not be extracted twice concurrently, but it must be re-runnable after a
    prompt change, so a plain UniqueConstraint is wrong. It is enforced in
    ``enqueue_job`` under a row lock on the document rather than as a partial
    unique index: Alembic's autogenerate does not reliably compare a partial
    index's ``WHERE`` clause, so one would turn ``make migrate-check`` into a
    source of false drift, and at 1–3 bills at a time the lock costs nothing.
    """

    __tablename__ = "bill_jobs"
    __table_args__ = (
        # A typo in a status or kind string would otherwise create a job that no
        # query ever claims or reaps. Built from the constants so they cannot
        # drift; the migration spells the same lists out literally.
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in JOB_STATUSES) + ")",
            name="ck_bill_jobs_status",
        ),
        CheckConstraint(f"kind IN ('{JOB_KIND_EXTRACT}')", name="ck_bill_jobs_kind"),
        # What the claim query filters on. A partial index on status = 'queued'
        # would be smaller; at this volume it is not worth the migration
        # complexity.
        Index("ix_bill_jobs_claimable", "status", "run_after"),
        # Backs the one-active-job-per-document check in enqueue_job.
        Index("ix_bill_jobs_document_kind", "document_id", "kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    place_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("places.id", ondelete="CASCADE")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bill_documents.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default=JOB_QUEUED)
    # Incremented on claim, not on completion, so a job whose worker is killed
    # mid-flight still spends an attempt — otherwise a job that crashes the
    # process every time would be requeued forever.
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    # Not claimable before this. Pushed out by the backoff after a failure.
    run_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
