"""The extraction envelope: what ``submit_extraction`` accepts (#57).

Every value the agent reads off a bill carries where it read it. Header values
are wrapped one by one in ``Field[T]``; a line item or a meter reading is one
printed row, so the row carries one span for all of its columns — #24's
highlight marks the row, and asking the model for eleven copies of the same
line per row would cost tokens and buy nothing.

The rule that makes the spans worth having: **a value without a span is
rejected.** If the model says it read something, it must say where — page and
the text as printed. A value it could not find is ``null``, and only then may
the span be ``null`` too.

Field names mirror the ``bills`` / ``bill_line_items`` / ``bill_meter_readings``
columns from #52/#53, so #60 maps this onto rows without a translation layer.
"""

from datetime import date
from decimal import Decimal

import pydantic
from pydantic import BaseModel, ConfigDict, model_validator

from app.schemas.bill import DocumentTypeLiteral, ReadMethodLiteral
from app.schemas.bill_line_item import ChargeKindLiteral


class Sourced(BaseModel):
    """Where a value was read, and how sure the model is of it."""

    model_config = ConfigDict(extra="forbid")

    confidence: float = pydantic.Field(
        ge=0, le=1, description="0..1 — how sure you are this was read correctly."
    )
    source_page: int | None = pydantic.Field(
        default=None, ge=1, description="1-based page the value was read from."
    )
    source_text: str | None = pydantic.Field(
        default=None,
        min_length=1,
        description="The line exactly as printed, copied from get_page_text.",
    )

    def _has_value(self) -> bool:
        return True

    @model_validator(mode="after")
    def _a_value_needs_a_span(self):
        if self._has_value() and (self.source_page is None or self.source_text is None):
            raise ValueError(
                "a value was given without source_page and source_text — quote the "
                "line it was read from, or set the value to null if it is not printed"
            )
        return self


class Field[T](Sourced):
    """One extracted header value. ``value`` is null when the bill does not print it."""

    value: T | None

    def _has_value(self) -> bool:
        return self.value is not None


class LineItem(Sourced):
    """One printed charge line, or a printed subtotal of them."""

    line_no: int = pydantic.Field(ge=1, description="Position on the bill, from 1.")
    charge_kind: ChargeKindLiteral
    raw_label: str = pydantic.Field(min_length=1, description="The label verbatim.")
    quantity: Decimal | None = None
    unit: str | None = None
    unit_price: Decimal | None = None
    net_amount: Decimal
    tax_amount: Decimal | None = None
    period_start: date | None = None
    period_end: date | None = None
    is_subtotal: bool = False


class MeterReading(Sourced):
    """One meter register's index pair."""

    pod_code: str | None = None
    meter_serial: str | None = None
    # Aliased: ``register`` is a classmethod on every pydantic model. The JSON
    # the model sends, and model_dump(by_alias=True), still say ``register``.
    register_: str | None = pydantic.Field(default=None, alias="register")
    index_previous: Decimal | None = None
    index_current: Decimal | None = None
    multiplier: Decimal | None = None
    read_method: ReadMethodLiteral
    read_on: date | None = None
    quantity: Decimal


class ExtractionEnvelope(BaseModel):
    """Everything ``submit_extraction`` takes. Validated on submit; a rejection
    goes back to the model as a tool error it can correct."""

    model_config = ConfigDict(extra="forbid")

    document_type: Field[DocumentTypeLiteral]
    provider_name: Field[str]
    provider_tax_id: Field[str]
    customer_code: Field[str]
    provider_invoice_series: Field[str]
    provider_invoice_number: Field[str]
    # Only on a credit note: the invoice it reverses.
    corrects_invoice_number: Field[str]
    issued_on: Field[date]
    due_on: Field[date]
    period_start: Field[date]
    period_end: Field[date]
    consumption: Field[Decimal]
    unit: Field[str]
    currency_code: Field[str]
    net_amount: Field[Decimal]
    vat_base: Field[Decimal]
    # A fraction: 0.19, not 19.
    vat_rate: Field[Decimal]
    vat_amount: Field[Decimal]
    total_amount: Field[Decimal]
    balance_brought_forward: Field[Decimal]
    total_due: Field[Decimal]
    read_method: Field[ReadMethodLiteral]
    line_items: list[LineItem]
    meter_readings: list[MeterReading]

    @model_validator(mode="after")
    def _line_numbers_are_unique(self):
        numbers = [item.line_no for item in self.line_items]
        if len(numbers) != len(set(numbers)):
            raise ValueError("line_items: line_no must be unique")
        return self

    @model_validator(mode="after")
    def _vat_rate_is_a_fraction(self):
        # 19 for 19 % is the commonest slip, and it would pass every other check.
        rate = self.vat_rate.value
        if rate is not None and not (0 <= rate < 1):
            raise ValueError("vat_rate is a fraction: 0.19 for 19 %, not 19")
        return self
