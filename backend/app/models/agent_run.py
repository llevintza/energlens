import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# The run record for the extraction agent (#56, part of #51). Written by
# app/agent/recorder.py; nothing else writes agent_runs or agent_steps.
#
# Volume: at 1–3 bills at a time this is tens of agent_runs rows a month and a
# few hundred agent_steps — Neon's free tier holds that for years, so there are
# deliberately no rollups, no partitioning and no retention job.
# Revisit when: a second user arrives, or an eval loop runs on every commit.

RUN_KIND_EXTRACT = "extract"
RUN_KINDS = (RUN_KIND_EXTRACT,)

RUN_RUNNING = "running"
RUN_SUCCEEDED = "succeeded"
RUN_FAILED = "failed"
RUN_REFUSED = "refused"
RUN_OVER_BUDGET = "over_budget"
RUN_STATUSES = (RUN_RUNNING, RUN_SUCCEEDED, RUN_FAILED, RUN_REFUSED, RUN_OVER_BUDGET)

EFFORTS = ("low", "medium", "high", "xhigh", "max")

ERROR_KINDS = ("rate_limit", "overloaded", "timeout", "schema_invalid", "internal")

STEP_KINDS = ("assistant", "tool_use", "tool_result")

SCORE_KINDS = ("model_confidence", "human_accepted", "human_edited", "golden_match")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


class AgentRun(Base):
    """One run of the agent loop: what it cost, how long it took, how it ended.

    ``is_eval`` is the only thing separating eval runs from production — both
    write the same schema (#51), so every dashboard query filters on it.

    The four token columns are the API's own ``usage`` field names. There is no
    thinking-token column: thinking is billed as output.
    """

    __tablename__ = "agent_runs"
    __table_args__ = (
        # Built from the constants so they cannot drift; the migration spells
        # the same lists out literally.
        CheckConstraint(_in("kind", RUN_KINDS), name="ck_agent_runs_kind"),
        CheckConstraint(_in("status", RUN_STATUSES), name="ck_agent_runs_status"),
        CheckConstraint(_in("effort", EFFORTS), name="ck_agent_runs_effort"),
        CheckConstraint(_in("error_kind", ERROR_KINDS), name="ck_agent_runs_error_kind"),
        Index("ix_agent_runs_started_at", "started_at"),
        Index("ix_agent_runs_is_eval_started", "is_eval", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(30))
    is_eval: Mapped[bool] = mapped_column(Boolean, default=False)
    # SET NULL rather than CASCADE: a run is the record of money spent, and it
    # outlives the job or document it was about.
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("bill_jobs.id", ondelete="SET NULL", name="fk_agent_runs_job_id")
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "bill_documents.id", ondelete="SET NULL", name="fk_agent_runs_document_id"
        )
    )
    model: Mapped[str] = mapped_column(String(60))
    # The region profile (#57) and a hash or tag of prompt + profile, so a
    # prompt change is visible in the data. Nullable until #57 supplies them.
    profile: Mapped[str | None] = mapped_column(String(60))
    prompt_version: Mapped[str | None] = mapped_column(String(40))
    effort: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default=RUN_RUNNING)
    # The API's own value — end_turn, max_tokens, tool_use, refusal, … — so
    # open-ended, with no CHECK.
    stop_reason: Mapped[str | None] = mapped_column(String(30))
    refusal_category: Mapped[str | None] = mapped_column(String(40))
    turns: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_creation_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    # Six decimals: a run costs ~$0.01. NULL, never 0, when the model has no
    # entry in app/agent/pricing.py — "unknown" must not read as "free".
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_kind: Mapped[str | None] = mapped_column(String(40))
    error_detail: Mapped[str | None] = mapped_column(Text)


class AgentStep(Base):
    """One step of a run, in order. For debugging, not a second copy of the PDF:
    ``detail`` is truncated before it is written."""

    __tablename__ = "agent_steps"
    __table_args__ = (
        UniqueConstraint("run_id", "seq", name="uq_agent_steps_run_seq"),
        CheckConstraint(_in("kind", STEP_KINDS), name="ck_agent_steps_kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE", name="fk_agent_steps_run_id")
    )
    seq: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20))
    tool_name: Mapped[str | None] = mapped_column(String(60))
    ok: Mapped[bool | None] = mapped_column(Boolean)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AgentScore(Base):
    """A per-field score of a run's output.

    ``confidence_at_propose`` on the ``human_accepted`` row is the whole point:
    it is what the calibration curve in #62 plots against, without a join
    through two tables and a timestamp guess. #60 writes it.
    """

    __tablename__ = "agent_scores"
    __table_args__ = (
        CheckConstraint(_in("kind", SCORE_KINDS), name="ck_agent_scores_kind"),
        Index("ix_agent_scores_run_kind", "run_id", "kind"),
        Index("ix_agent_scores_field_kind", "field", "kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE", name="fk_agent_scores_run_id")
    )
    # The dotted path into the extraction envelope: total_amount,
    # line_items[3].unit_price, …
    field: Mapped[str] = mapped_column(String(60))
    kind: Mapped[str] = mapped_column(String(30))
    value: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    confidence_at_propose: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
