"""The extraction agent's tools (#57).

Built per run by ``ExtractionTools``, bound to that run's PDF text and context.
They are also the metric surface: every call's ``tool_name``, ``ok`` and
``duration_ms`` becomes an agent_steps row (#62 plots the mix), which
app/agent/extract.py writes from the timings collected here.

A tool reports a problem the model can fix — a page that does not exist, a
payload that fails validation — by raising ``ToolError``, which the SDK's
runner returns as an ``is_error`` tool result. Any other exception is caught by
the runner the same way, so a tool that crashes costs the model a turn, not the
run.
"""

import json
import time
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace

import pydantic
from anthropic import beta_async_tool
from anthropic.lib.tools import ToolError
from pydantic import BaseModel

from app.agent.context import ExtractionContext
from app.agent.envelope import ExtractionEnvelope
from app.schemas.bill_line_item import ChargeKindLiteral
from app.services import bill_math

TWO_PLACES = Decimal("0.01")


def page_texts(pdf: bytes) -> list[str]:
    """pypdf's text layer, one string per page. An unreadable PDF has none —
    the model still has the document itself, and get_page_text says so."""
    from pypdf import PdfReader

    try:
        reader = PdfReader(BytesIO(pdf))
        return [page.extract_text() or "" for page in reader.pages]
    except Exception:
        return []


def validation_summary(exc: pydantic.ValidationError) -> str:
    """One line per error, ``line_items.3.source_text: ...`` — pydantic's own
    str() adds a docs URL to every error, which the model pays for in tokens."""
    return "\n".join(
        f"- {'.'.join(str(p) for p in err['loc']) or '(payload)'}: {err['msg']}"
        for err in exc.errors()
    )


class ArithmeticLine(BaseModel):
    charge_kind: ChargeKindLiteral
    net_amount: Decimal
    is_subtotal: bool = False


def _num(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _check(expected: Decimal, stated: Decimal) -> dict:
    delta = stated - expected
    return {
        "expected": str(expected),
        "stated": str(stated),
        "delta": str(delta),
        "within_tolerance": abs(delta) < bill_math.RECONCILE_TOLERANCE,
    }


class ExtractionTools:
    def __init__(self, *, pages: list[str], context: ExtractionContext) -> None:
        self.pages = pages
        self.context = context
        # Set by a submit_extraction that validated; the loop stops on it.
        self.submitted: ExtractionEnvelope | None = None
        # (tool_name, duration_ms) in call order, for each call whose body ran.
        # A call the SDK rejects before the body (bad arguments) has none.
        self.timings: list[tuple[str, int]] = []

    def _timed(self, name: str, t0: float) -> None:
        self.timings.append((name, int((time.monotonic() - t0) * 1000)))

    def all(self) -> list:
        tools = self

        @beta_async_tool
        async def get_page_text(page: int) -> str:
            """Return the text layer of one page of the bill.

            Args:
                page: 1-based page number.
            """
            t0 = time.monotonic()
            try:
                if not tools.pages:
                    raise ToolError(
                        "this PDF has no text layer; read the attached document instead"
                    )
                if not 1 <= page <= len(tools.pages):
                    raise ToolError(f"page {page} does not exist; the bill has {len(tools.pages)}")
                return tools.pages[page - 1]
            finally:
                tools._timed("get_page_text", t0)

        @beta_async_tool
        async def get_place_context() -> str:
            """Return what is known about the place this bill is for: country,
            currency, the provider on its latest bill, contracted power and
            tariff name. null means not known — not zero."""
            t0 = time.monotonic()
            try:
                return json.dumps(tools.context.place_dict())
            finally:
                tools._timed("get_place_context", t0)

        @beta_async_tool
        async def get_prior_bill() -> str:
            """Return the previous bill on file for this place: invoice series and
            number, period, consumption, total, effective price per unit, and the
            meter index it ended on. Use index continuity to tell a real read
            from an estimate, and the invoice number to link a credit note."""
            t0 = time.monotonic()
            try:
                prior = tools.context.prior_bill_dict()
                return json.dumps(prior) if prior else "No prior bill on file for this place."
            finally:
                tools._timed("get_prior_bill", t0)

        @beta_async_tool
        async def check_arithmetic(
            line_items: list[ArithmeticLine],
            net_amount: Decimal | None = None,
            vat_base: Decimal | None = None,
            vat_rate: Decimal | None = None,
            vat_amount: Decimal | None = None,
            total_amount: Decimal | None = None,
        ) -> str:
            """Add up your line items and check them against the printed totals.

            Subtotal lines and vat lines are left out of the line sum. Returns
            the computed sums and, for each total you pass, the difference from
            it. Advisory: it never rejects anything.

            Args:
                line_items: Your lines: charge_kind, net_amount, is_subtotal.
                net_amount: The printed total before VAT.
                vat_base: The printed VAT base.
                vat_rate: The printed VAT rate as a fraction (0.19).
                vat_amount: The printed VAT amount.
                total_amount: The printed invoice total.
            """
            t0 = time.monotonic()
            try:
                recon = bill_math.reconcile(
                    SimpleNamespace(net_amount=net_amount), line_items
                )
                result: dict = {
                    "computed_net": str(recon.computed_net),
                    "stated_net": _num(recon.stated_net),
                    "net_delta": _num(recon.delta),
                    "net_within_tolerance": recon.within_tolerance,
                    "by_charge_kind": {
                        k: str(v) for k, v in bill_math.by_charge_kind(line_items).items()
                    },
                    "subtotal_lines_excluded": sum(1 for i in line_items if i.is_subtotal),
                }
                if vat_base is not None and vat_rate is not None and vat_amount is not None:
                    expected = (vat_base * vat_rate).quantize(TWO_PLACES)
                    result["vat_check"] = _check(expected, vat_amount)
                if net_amount is not None and vat_amount is not None and total_amount is not None:
                    result["total_check"] = _check(net_amount + vat_amount, total_amount)
                return json.dumps(result)
            finally:
                tools._timed("check_arithmetic", t0)

        @beta_async_tool(input_schema=ExtractionEnvelope)
        async def submit_extraction(**payload) -> str:
            """Submit the finished extraction. This ends the run once it is
            accepted. Every value needs a confidence, and every non-null value a
            source_page and source_text; a rejected payload comes back with the
            reasons, to correct and submit again."""
            t0 = time.monotonic()
            try:
                try:
                    envelope = ExtractionEnvelope.model_validate(payload)
                except pydantic.ValidationError as exc:
                    raise ToolError(
                        "Rejected. Fix these and submit again:\n" + validation_summary(exc)
                    ) from exc
                tools.submitted = envelope
                return "Accepted."
            finally:
                tools._timed("submit_extraction", t0)

        return [get_page_text, get_place_context, get_prior_bill, check_arithmetic, submit_extraction]
