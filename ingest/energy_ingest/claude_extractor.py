"""PDF → ExtractedBill via Claude's native PDF understanding.

Each PDF is sent as a base64 document block to messages.parse() with the
ExtractedBill schema as the output format — no text-extraction layer needed.
Results are cached in a JSONL file keyed by file content hash, so re-runs
never re-pay API calls.
"""

import base64
import hashlib
import json
from pathlib import Path

from anthropic import Anthropic

from energy_ingest.models import ExtractedBill

MODEL = "claude-opus-5"

PROMPT = """\
Extract the billing data from this electricity bill.

Rules:
- period_start/period_end are the consumption period being billed, not the \
issue or due date.
- consumption_kwh is the electricity consumed in this period. If the bill \
splits consumption into day/night or peak/off-peak bands, sum them.
- unit_price is the energy price per kWh as printed. If multiple tariff bands \
exist, leave it null and mention the bands in confidence_notes.
- fixed_charges covers subscription/standing/network charges; taxes covers \
VAT, excise and levies.
- total_amount is the amount due for THIS bill (not the account balance).
- Amounts can be negative on credit notes.
- Use confidence_notes for anything estimated, ambiguous, or unusual; \
otherwise leave it null.
"""


class ExtractionError(Exception):
    pass


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_cache(cache_path: Path) -> dict[str, dict]:
    cache: dict[str, dict] = {}
    if cache_path.exists():
        for line in cache_path.read_text().splitlines():
            if line.strip():
                entry = json.loads(line)
                cache[entry["sha256"]] = entry
    return cache


def append_cache(cache_path: Path, entry: dict) -> None:
    with cache_path.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def extract_bill(client: Anthropic, pdf_path: Path) -> ExtractedBill:
    pdf_b64 = base64.standard_b64encode(pdf_path.read_bytes()).decode()

    # Thinking is on by default on claude-opus-5 and shares the max_tokens
    # budget with the output; low effort keeps it from eating the budget on
    # what is a simple form-extraction task.
    response = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        output_config={"effort": "low"},
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                    {"type": "text", "text": PROMPT},
                ],
            }
        ],
        output_format=ExtractedBill,
    )

    if response.stop_reason == "refusal":
        raise ExtractionError(f"Claude declined to process {pdf_path.name}")
    if response.parsed_output is None:
        raise ExtractionError(f"No structured output returned for {pdf_path.name}")
    return response.parsed_output


def extract_directory(
    client: Anthropic, pdf_dir: Path, cache_path: Path
) -> list[tuple[Path, ExtractedBill]]:
    """Extract every PDF in a directory, reusing cached results by file hash."""
    cache = load_cache(cache_path)
    results: list[tuple[Path, ExtractedBill]] = []

    for pdf_path in sorted(pdf_dir.glob("*.pdf")):
        digest = file_sha256(pdf_path)
        if digest in cache:
            bill = ExtractedBill.model_validate(cache[digest]["bill"])
        else:
            bill = extract_bill(client, pdf_path)
            append_cache(
                cache_path,
                {
                    "sha256": digest,
                    "file": pdf_path.name,
                    "bill": bill.model_dump(mode="json"),
                },
            )
        results.append((pdf_path, bill))
    return results
