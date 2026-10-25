import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class BillMeterReading(Base):
    """A meter index pair a bill was computed from, one row per register."""

    __tablename__ = "bill_meter_readings"
    __table_args__ = (
        # Same values as ck_bills_read_method — the enum is ReadMethod in
        # app/models/bill.py. The list is repeated here, and
        # tests/test_bill_line_items.py fails if the two drift.
        CheckConstraint(
            "read_method IN ('actual', 'self_read', 'estimated', "
            "'regularisation', 'mixed')",
            name="ck_bill_meter_readings_read_method",
        ),
        Index("ix_bill_meter_readings_bill_id", "bill_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Named by hand: Base configures no naming convention.
    bill_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "bills.id", ondelete="CASCADE", name="fk_bill_meter_readings_bill_id"
        )
    )
    # The EU point-of-delivery id: RO001E107927758. The stable identity of a
    # connection point across supplier changes, when the bills look nothing alike.
    pod_code: Mapped[str | None] = mapped_column(String(40))
    meter_serial: Mapped[str | None] = mapped_column(String(50))
    # "Cod ELECTEL" on the corpus.
    grid_operator_code: Mapped[str | None] = mapped_column(String(40))
    # day / night / peak. Free text, not an enum: register names are a property
    # of the tariff, and RO residential meters have only one.
    register: Mapped[str | None] = mapped_column(String(20))
    index_previous: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    index_current: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    # "Const." — the meter constant the index difference is multiplied by.
    multiplier: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    read_method: Mapped[str] = mapped_column(String(20))
    read_on: Mapped[date | None] = mapped_column(Date)
    # "Cantitate de facturat" — what was billed, which a regularisation can
    # make differ from the index difference.
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    bill: Mapped["Bill"] = relationship(back_populates="meter_readings")  # noqa: F821
