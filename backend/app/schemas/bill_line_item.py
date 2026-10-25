import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Must match ChargeKind in app/models/bill_line_item.py, its CheckConstraint, and
# ChargeKind in frontend/src/api/types.ts. tests/test_bill_line_items.py pins all four.
ChargeKindLiteral = Literal[
    "energy",
    "supply",
    "transmission",
    "distribution",
    "system_services",
    "cogeneration",
    "green_certificates",
    "capacity",
    "levy",
    "excise",
    "vat",
    "standing_charge",
    "reactive_energy",
    "metering",
    "discount",
    "balance",
    "other",
]


class BillLineItemBase(BaseModel):
    line_no: int
    charge_kind: ChargeKindLiteral
    raw_label: str = Field(max_length=200)
    quantity: Decimal | None = None
    unit: str | None = Field(default=None, max_length=10)
    # No ge=0: discount lines are negative, and so is every line of a credit note.
    unit_price: Decimal | None = None
    net_amount: Decimal
    tax_amount: Decimal | None = None
    period_start: date | None = None
    period_end: date | None = None
    is_subtotal: bool = False

    @model_validator(mode="after")
    def check_period(self) -> "BillLineItemBase":
        if (
            self.period_start is not None
            and self.period_end is not None
            and self.period_end < self.period_start
        ):
            raise ValueError("period_end must not be before period_start")
        return self


class BillLineItemCreate(BillLineItemBase):
    pass


class BillLineItemRead(BillLineItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    bill_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
