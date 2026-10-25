import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ChargeKind(StrEnum):
    """The canonical, cross-region taxonomy a charge line is grouped by.

    Closed on purpose: analytics group by it. The provider's own wording lives
    in ``raw_label`` beside it, and the label → kind mapping belongs to the
    region profile the extraction agent reads (#57), never to the database.
    ``other`` is not a failure state — an unseen charge is stored under its real
    label and grouped here until someone decides it deserves a kind.
    """

    ENERGY = "energy"
    SUPPLY = "supply"
    TRANSMISSION = "transmission"
    DISTRIBUTION = "distribution"
    SYSTEM_SERVICES = "system_services"
    COGENERATION = "cogeneration"
    GREEN_CERTIFICATES = "green_certificates"
    CAPACITY = "capacity"
    LEVY = "levy"
    EXCISE = "excise"
    VAT = "vat"
    STANDING_CHARGE = "standing_charge"
    REACTIVE_ENERGY = "reactive_energy"
    METERING = "metering"
    DISCOUNT = "discount"
    BALANCE = "balance"
    OTHER = "other"


class BillLineItem(Base):
    """One printed charge line, or a printed subtotal of them."""

    __tablename__ = "bill_line_items"
    __table_args__ = (
        UniqueConstraint("bill_id", "line_no", name="uq_bill_line_items_bill_line"),
        CheckConstraint(
            "charge_kind IN ('energy', 'supply', 'transmission', 'distribution', "
            "'system_services', 'cogeneration', 'green_certificates', 'capacity', "
            "'levy', 'excise', 'vat', 'standing_charge', 'reactive_energy', "
            "'metering', 'discount', 'balance', 'other')",
            name="ck_bill_line_items_charge_kind",
        ),
        # A comparison with NULL is not false, so lines with no sub-period of
        # their own — most of them — pass.
        CheckConstraint(
            "period_end >= period_start", name="ck_bill_line_items_period_order"
        ),
        Index("ix_bill_line_items_bill_id", "bill_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Named by hand: Base configures no naming convention.
    bill_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bills.id", ondelete="CASCADE", name="fk_bill_line_items_bill_id")
    )
    line_no: Mapped[int] = mapped_column(Integer)
    charge_kind: Mapped[str] = mapped_column(String(30))
    # Verbatim — "Certificate verzi". Never translated, never normalised.
    raw_label: Mapped[str] = mapped_column(String(200))
    # Subtotal lines carry neither a quantity nor a price.
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    unit: Mapped[str | None] = mapped_column(String(10))
    # 8 dp, not the bills table's 6: the corpus prints 0,0725416.
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(16, 8))
    net_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    # The per-line VAT as printed, when the layout prints one.
    tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    # A line's own sub-period, which can be narrower than the bill's: 2025-06
    # bills energy twice because the regulated price changed mid-period.
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    # Lines 7 and 12 of 2025-06. Summing them with the rest double-counts.
    is_subtotal: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    bill: Mapped["Bill"] = relationship(back_populates="line_items")  # noqa: F821
