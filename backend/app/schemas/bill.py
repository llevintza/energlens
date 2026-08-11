import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

UtilityTypeLiteral = Literal["electricity", "gas", "water"]


class BillBase(BaseModel):
    utility_type: UtilityTypeLiteral = "electricity"
    period_start: date
    period_end: date
    consumption: Decimal | None = Field(default=None, ge=0)
    unit: str = Field(default="kWh", max_length=10)
    unit_price: Decimal | None = Field(default=None, ge=0)
    fixed_charges: Decimal | None = None
    taxes: Decimal | None = None
    total_amount: Decimal
    provider_name: str | None = Field(default=None, max_length=100)
    raw_file_ref: str | None = Field(default=None, max_length=500)
    source: Literal["manual", "script", "ai"] = "manual"
    notes: str | None = None

    @model_validator(mode="after")
    def check_period(self) -> "BillBase":
        if self.period_end < self.period_start:
            raise ValueError("period_end must not be before period_start")
        return self


class BillCreate(BillBase):
    pass


class BillUpdate(BaseModel):
    utility_type: UtilityTypeLiteral | None = None
    period_start: date | None = None
    period_end: date | None = None
    consumption: Decimal | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=10)
    unit_price: Decimal | None = Field(default=None, ge=0)
    fixed_charges: Decimal | None = None
    taxes: Decimal | None = None
    total_amount: Decimal | None = None
    provider_name: str | None = Field(default=None, max_length=100)
    raw_file_ref: str | None = Field(default=None, max_length=500)
    source: Literal["manual", "script", "ai"] | None = None
    notes: str | None = None


class BillRead(BillBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    place_id: uuid.UUID
    currency_code: str
    created_at: datetime
    updated_at: datetime
