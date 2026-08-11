"""The extraction contract shared by phase 1 (local CLI) and phase 2 (server-side)."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class ExtractedBill(BaseModel):
    """Fields extracted from one electricity bill PDF."""

    period_start: date = Field(description="First day of the billing period")
    period_end: date = Field(description="Last day of the billing period")
    consumption_kwh: Decimal | None = Field(
        default=None, description="Electricity consumed in kWh, if stated"
    )
    unit_price: Decimal | None = Field(
        default=None,
        description="Price per kWh as printed on the bill (energy component only)",
    )
    fixed_charges: Decimal | None = Field(
        default=None,
        description="Fixed/subscription charges for the period (network fees, standing charges)",
    )
    taxes: Decimal | None = Field(
        default=None, description="Total taxes and levies (VAT, excise, etc.)"
    )
    total_amount: Decimal = Field(description="Total amount due for this bill")
    currency_code: str = Field(
        description="ISO 4217 currency code the bill is charged in, e.g. EUR or RON"
    )
    provider_name: str | None = Field(
        default=None, description="Name of the utility provider issuing the bill"
    )
    confidence_notes: str | None = Field(
        default=None,
        description="Anything ambiguous, estimated, or unusual about this bill "
        "that a human should double-check; null if everything was clear",
    )


class ValidationIssue(BaseModel):
    level: str  # "error" | "warning"
    message: str


def validate_bill(
    bill: ExtractedBill, expected_currency: str | None = None
) -> list[ValidationIssue]:
    """Sanity checks before anything is uploaded. Errors block; warnings don't."""
    issues: list[ValidationIssue] = []

    if bill.period_end < bill.period_start:
        issues.append(
            ValidationIssue(level="error", message="period_end before period_start")
        )
    else:
        days = (bill.period_end - bill.period_start).days + 1
        if not 20 <= days <= 95:
            issues.append(
                ValidationIssue(
                    level="warning",
                    message=f"unusual period length: {days} days",
                )
            )

    if expected_currency and bill.currency_code.upper() != expected_currency.upper():
        issues.append(
            ValidationIssue(
                level="error",
                message=(
                    f"bill currency {bill.currency_code} does not match "
                    f"the place's currency {expected_currency}"
                ),
            )
        )

    if (
        bill.consumption_kwh is not None
        and bill.unit_price is not None
        and bill.total_amount
    ):
        expected = (
            bill.consumption_kwh * bill.unit_price
            + (bill.fixed_charges or Decimal(0))
            + (bill.taxes or Decimal(0))
        )
        deviation = abs(expected - bill.total_amount) / abs(bill.total_amount)
        if deviation > Decimal("0.05"):
            issues.append(
                ValidationIssue(
                    level="warning",
                    message=(
                        f"components add up to {expected:.2f} but total is "
                        f"{bill.total_amount:.2f} ({deviation:.0%} off)"
                    ),
                )
            )

    return issues


def to_api_payload(bill: ExtractedBill, source_file: str) -> dict:
    """Shape an ExtractedBill into the POST /places/{id}/bills body."""

    def dec(value: Decimal | None) -> str | None:
        return str(value) if value is not None else None

    return {
        "utility_type": "electricity",
        "period_start": bill.period_start.isoformat(),
        "period_end": bill.period_end.isoformat(),
        "consumption": dec(bill.consumption_kwh),
        "unit": "kWh",
        "unit_price": dec(bill.unit_price),
        "fixed_charges": dec(bill.fixed_charges),
        "taxes": dec(bill.taxes),
        "total_amount": str(bill.total_amount),
        "provider_name": bill.provider_name,
        "raw_file_ref": source_file,
        "source": "script",
        "notes": bill.confidence_notes,
    }
