from datetime import date
from decimal import Decimal

from energlens_ingest.models import ExtractedBill, to_api_payload, validate_bill


def make_bill(**overrides) -> ExtractedBill:
    data = {
        "period_start": date(2026, 3, 1),
        "period_end": date(2026, 3, 31),
        "consumption_kwh": Decimal("250"),
        "unit_price": Decimal("0.20"),
        "fixed_charges": Decimal("5.90"),
        "taxes": Decimal("10.00"),
        "total_amount": Decimal("65.90"),
        "currency_code": "EUR",
        "provider_name": "EDP",
    }
    data.update(overrides)
    return ExtractedBill(**data)


class TestValidation:
    def test_clean_bill_passes(self):
        assert validate_bill(make_bill()) == []

    def test_inverted_period_is_error(self):
        issues = validate_bill(make_bill(period_end=date(2026, 2, 1)))
        assert any(i.level == "error" for i in issues)

    def test_short_period_warns(self):
        issues = validate_bill(make_bill(period_end=date(2026, 3, 5)))
        assert [i.level for i in issues] == ["warning"]

    def test_currency_mismatch_is_error(self):
        issues = validate_bill(make_bill(), expected_currency="RON")
        assert any(i.level == "error" for i in issues)

    def test_component_mismatch_warns(self):
        issues = validate_bill(make_bill(total_amount=Decimal("100.00")))
        assert [i.level for i in issues] == ["warning"]

    def test_negative_credit_note_allowed(self):
        issues = validate_bill(
            make_bill(
                consumption_kwh=None,
                unit_price=None,
                total_amount=Decimal("-12.50"),
            )
        )
        assert issues == []


class TestApiPayload:
    def test_decimals_serialized_as_strings(self):
        payload = to_api_payload(make_bill(), "2026-03.pdf")
        assert payload["consumption"] == "250"
        assert payload["total_amount"] == "65.90"
        assert payload["source"] == "script"
        assert payload["raw_file_ref"] == "2026-03.pdf"
        assert payload["period_start"] == "2026-03-01"

    def test_none_fields_stay_none(self):
        payload = to_api_payload(
            make_bill(consumption_kwh=None, unit_price=None), "x.pdf"
        )
        assert payload["consumption"] is None
        assert payload["unit_price"] is None
