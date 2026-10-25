"""bill_math without a database, the way test_series.py tests series.py."""

from decimal import Decimal

from app.services.bill_math import (
    RECONCILE_TOLERANCE,
    by_charge_kind,
    line_total,
    reconcile,
)


class FakeLine:
    def __init__(self, kind, net, subtotal=False):
        self.charge_kind = kind
        self.net_amount = Decimal(net)
        self.is_subtotal = subtotal


class FakeBill:
    def __init__(self, net):
        self.net_amount = Decimal(net) if net is not None else None


# All twelve lines of data/bills/2025-06.pdf, page 2 — synthetic, no PDF.
# Lines 7 and 12 are the printed subtotals.
LINES_2025_06 = [
    FakeLine("energy", "11.00"),
    FakeLine("energy", "33.61"),
    FakeLine("transmission", "5.82"),
    FakeLine("system_services", "0.50"),
    FakeLine("system_services", "0.93"),
    FakeLine("distribution", "51.76"),
    FakeLine("other", "103.62", subtotal=True),
    FakeLine("cogeneration", "0.62"),
    FakeLine("levy", "0.03"),
    FakeLine("green_certificates", "12.78"),
    FakeLine("excise", "1.28"),
    FakeLine("other", "118.33", subtotal=True),
]


class TestLineTotal:
    def test_subtotals_are_not_counted(self):
        assert line_total(LINES_2025_06) == Decimal("118.33")

    def test_empty_is_zero(self):
        assert line_total([]) == Decimal(0)

    def test_negative_lines_subtract(self):
        lines = [FakeLine("energy", "40.00"), FakeLine("discount", "-5.00")]
        assert line_total(lines) == Decimal("35.00")


class TestByChargeKind:
    def test_corpus_rollup(self):
        totals = by_charge_kind(LINES_2025_06)
        # The two energy lines are one charge at two prices.
        assert totals["energy"] == Decimal("44.61")
        assert totals["distribution"] == Decimal("51.76")
        assert totals["system_services"] == Decimal("1.43")
        assert sum(totals.values()) == Decimal("118.33")

    def test_subtotals_do_not_land_under_their_kind(self):
        assert "other" not in by_charge_kind(LINES_2025_06)

    def test_other_is_kept_not_dropped(self):
        lines = [FakeLine("energy", "10.00"), FakeLine("other", "2.50")]
        assert by_charge_kind(lines) == {
            "energy": Decimal("10.00"),
            "other": Decimal("2.50"),
        }


class TestReconcile:
    def test_corpus_reconciles(self):
        result = reconcile(FakeBill("118.33"), LINES_2025_06)
        assert result.computed_net == Decimal("118.33")
        assert result.stated_net == Decimal("118.33")
        assert result.delta == Decimal("0.00")
        assert result.within_tolerance is True

    def test_wrong_bill_is_flagged_not_raised(self):
        result = reconcile(FakeBill("120.00"), LINES_2025_06)
        assert result.within_tolerance is False
        # stated − computed, the sign ArithmeticCheck.tsx shows.
        assert result.delta == Decimal("1.67")

    def test_a_cent_is_rounding(self):
        assert reconcile(FakeBill("118.34"), LINES_2025_06).within_tolerance is True

    def test_tolerance_matches_the_frontend(self):
        assert RECONCILE_TOLERANCE == Decimal("0.015")
        lines = [FakeLine("energy", "10.000")]
        assert reconcile(FakeBill("10.015"), lines).within_tolerance is False
        assert reconcile(FakeBill("10.014"), lines).within_tolerance is True

    def test_no_stated_net_is_unknown_not_a_failure(self):
        result = reconcile(FakeBill(None), LINES_2025_06)
        assert result.computed_net == Decimal("118.33")
        assert result.stated_net is None
        assert result.delta is None
        assert result.within_tolerance is None
