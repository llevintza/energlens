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


class Bill(Base):
    __tablename__ = "bills"
    __table_args__ = (
        CheckConstraint("period_end >= period_start", name="ck_bills_period_order"),
        CheckConstraint(
            "source IN ('manual', 'script', 'ai')", name="ck_bills_source"
        ),
        UniqueConstraint(
            "place_id",
            "utility_type",
            "period_start",
            "period_end",
            name="uq_bills_place_period",
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    place: Mapped["Place"] = relationship(back_populates="bills")  # noqa: F821
