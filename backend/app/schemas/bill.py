import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

UtilityTypeLiteral = Literal["electricity", "gas", "water"]
DocumentTypeLiteral = Literal["invoice", "credit_note"]
ReadMethodLiteral = Literal[
    "actual", "self_read", "estimated", "regularisation", "mixed"
]


class BillBase(BaseModel):
    utility_type: UtilityTypeLiteral = "electricity"
    period_start: date
    period_end: date
    # No ge=0: a credit note bills -41 kWh, and refusing it is what made two of
    # the thirty bills in the corpus unstorable.
    consumption: Decimal | None = None
    unit: str = Field(default="kWh", max_length=10)
    # unit_price keeps ge=0 — a negative tariff is still nonsense.
    unit_price: Decimal | None = Field(default=None, ge=0)
    fixed_charges: Decimal | None = None
    taxes: Decimal | None = None
    total_amount: Decimal
    provider_name: str | None = Field(default=None, max_length=100)
    raw_file_ref: str | None = Field(default=None, max_length=500)
    source: Literal["manual", "script", "ai"] = "manual"
    notes: str | None = None

    # --- what the invoice itself says -------------------------------------
    provider_invoice_series: str | None = Field(default=None, max_length=20)
    provider_invoice_number: str | None = Field(default=None, max_length=50)
    issued_on: date | None = None
    due_on: date | None = None
    net_amount: Decimal | None = None
    vat_base: Decimal | None = None
    # A fraction, not a percentage. The column is Numeric(5, 4), so a caller
    # sending 21 for "21%" would otherwise overflow into a 500.
    vat_rate: Decimal | None = Field(default=None, ge=0, le=1)
    vat_amount: Decimal | None = None
    balance_brought_forward: Decimal | None = None
    total_due: Decimal | None = None
    read_method: ReadMethodLiteral | None = None
    document_type: DocumentTypeLiteral = "invoice"
    corrects_bill_id: uuid.UUID | None = None
    customer_code: str | None = Field(default=None, max_length=50)
    provider_tax_id: str | None = Field(default=None, max_length=30)
    # The uploaded PDF this bill came from, if any. Nullable and SET NULL on the
    # column: the bill outlives the document.
    document_id: uuid.UUID | None = None

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
    consumption: Decimal | None = None
    unit: str | None = Field(default=None, max_length=10)
    unit_price: Decimal | None = Field(default=None, ge=0)
    fixed_charges: Decimal | None = None
    taxes: Decimal | None = None
    total_amount: Decimal | None = None
    provider_name: str | None = Field(default=None, max_length=100)
    raw_file_ref: str | None = Field(default=None, max_length=500)
    source: Literal["manual", "script", "ai"] | None = None
    notes: str | None = None
    provider_invoice_series: str | None = Field(default=None, max_length=20)
    provider_invoice_number: str | None = Field(default=None, max_length=50)
    issued_on: date | None = None
    due_on: date | None = None
    net_amount: Decimal | None = None
    vat_base: Decimal | None = None
    vat_rate: Decimal | None = Field(default=None, ge=0, le=1)
    vat_amount: Decimal | None = None
    balance_brought_forward: Decimal | None = None
    total_due: Decimal | None = None
    read_method: ReadMethodLiteral | None = None
    document_type: DocumentTypeLiteral | None = None
    corrects_bill_id: uuid.UUID | None = None
    customer_code: str | None = Field(default=None, max_length=50)
    provider_tax_id: str | None = Field(default=None, max_length=30)
    document_id: uuid.UUID | None = None


class BillRead(BillBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    place_id: uuid.UUID
    currency_code: str
    created_at: datetime
    updated_at: datetime
