import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class UtilityType(StrEnum):
    ELECTRICITY = "electricity"
    GAS = "gas"
    WATER = "water"


class BillSource(StrEnum):
    MANUAL = "manual"
    SCRIPT = "script"
    AI = "ai"


class DocumentType(StrEnum):
    INVOICE = "invoice"
    CREDIT_NOTE = "credit_note"


class ReadMethod(StrEnum):
    """How the index behind the consumption figure was arrived at.

    An estimated read followed by a regularisation is the commonest cause of an
    apparent consumption spike, so this is the column that stops a chart lying.
    """

    ACTUAL = "actual"                  # the distributor read the meter
    SELF_READ = "self_read"            # "Autocitire"
    ESTIMATED = "estimated"            # "Estimare"
    REGULARISATION = "regularisation"  # "Regularizare"
    MIXED = "mixed"                    # "Regularizare + Autocitire" — printed as such


class Bill(Base):
    __tablename__ = "bills"
    __table_args__ = (
        CheckConstraint("period_end >= period_start", name="ck_bills_period_order"),
        CheckConstraint(
            "source IN ('manual', 'script', 'ai')", name="ck_bills_source"
        ),
        CheckConstraint(
            "document_type IN ('invoice', 'credit_note')",
            name="ck_bills_document_type",
        ),
        # NULL is neither in nor not in the list, so the bare form permits it —
        # same shape as ck_bills_source, and read_method is nullable.
        CheckConstraint(
            "read_method IN ('actual', 'self_read', 'estimated', "
            "'regularisation', 'mixed')",
            name="ck_bills_read_method",
        ),
        # A billing period does not identify an invoice: a Stornare reverses one
        # and prints the same period, so the period constraint this replaces made
        # the correction unstorable. PostgreSQL counts NULLs in a UNIQUE tuple as
        # distinct, which leaves manually-entered bills — no invoice number —
        # unconstrained here; app/routers/bills.py holds the period rule for them.
        UniqueConstraint(
            "place_id",
            "provider_invoice_series",
            "provider_invoice_number",
            name="uq_bills_place_invoice",
        ),
        Index("ix_bills_place_period_start", "place_id", "period_start"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    place_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("places.id", ondelete="CASCADE")
    )
    utility_type: Mapped[str] = mapped_column(
        String(20), default=UtilityType.ELECTRICITY, server_default="electricity"
    )
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    consumption: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    unit: Mapped[str] = mapped_column(String(10), default="kWh", server_default="kWh")
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    fixed_charges: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    taxes: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency_code: Mapped[str] = mapped_column(String(3))
    provider_name: Mapped[str | None] = mapped_column(String(100))
    raw_file_ref: Mapped[str | None] = mapped_column(String(500))
    source: Mapped[str] = mapped_column(String(10), default=BillSource.MANUAL)
    notes: Mapped[str | None] = mapped_column(Text)

    # --- what the invoice itself says -------------------------------------
    # Nullable throughout: a bill typed in by hand has none of it, and a bill
    # already uploaded by the CLI predates all of it.
    provider_invoice_series: Mapped[str | None] = mapped_column(String(20))
    provider_invoice_number: Mapped[str | None] = mapped_column(String(50))
    issued_on: Mapped[date | None] = mapped_column(Date)
    due_on: Mapped[date | None] = mapped_column(Date)
    net_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    # Not derivable from net_amount: 2026-07 prints a 555,87 net against a
    # 554,97 taxable base.
    vat_base: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    # A column, never a constant — the corpus is 19% until 2026-07, then 21%.
    vat_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    vat_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    balance_brought_forward: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    # total_amount stays the invoice's own value; this is what is payable once
    # the carried balance is applied, and the two differ whenever one exists.
    total_due: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    read_method: Mapped[str | None] = mapped_column(String(20))
    document_type: Mapped[str] = mapped_column(
        String(20), default=DocumentType.INVOICE, server_default="invoice"
    )
    # SET NULL, not CASCADE as everywhere else in this schema: deleting an
    # original must not silently delete the credit note documenting its
    # reversal. Named by hand — Base configures no naming convention, so an
    # unnamed constraint gets a generated name no later migration can drop.
    # Deliberately no ORM relationship: nothing traverses it yet, and a
    # self-referential edge would join the unit-of-work that DELETE /users/me
    # already walks through cascade="all, delete-orphan".
    corrects_bill_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("bills.id", ondelete="SET NULL", name="fk_bills_corrects_bill_id")
    )
    customer_code: Mapped[str | None] = mapped_column(String(50))
    # Tells PPC Energie Muntenia S.A. from PPC Energie S.A. across the 2025-03
    # handover, which provider_name alone does not survive.
    provider_tax_id: Mapped[str | None] = mapped_column(String(30))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    place: Mapped["Place"] = relationship(back_populates="bills")  # noqa: F821
