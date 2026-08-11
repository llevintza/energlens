"""energlens-ingest — extract bill data from PDFs and push it to the API.

    energlens-ingest extract --dir ./bills --cache extracted.jsonl [--dry-run]
    energlens-ingest upload  --cache extracted.jsonl --place-id <uuid>
    energlens-ingest run     --dir ./bills --place-id <uuid>       # extract + upload
"""

from pathlib import Path
from typing import Annotated

import typer
from anthropic import Anthropic
from rich.console import Console
from rich.table import Table

from energlens_ingest.api_client import EnerglensClient
from energlens_ingest.claude_extractor import ExtractedBill, extract_directory
from energlens_ingest.models import to_api_payload, validate_bill

app = typer.Typer(help=__doc__, add_completion=False)
console = Console()

DirOpt = Annotated[Path, typer.Option("--dir", help="Directory of bill PDFs")]
CacheOpt = Annotated[
    Path, typer.Option("--cache", help="JSONL extraction cache file")
]
PlaceOpt = Annotated[str, typer.Option("--place-id", help="Target place UUID")]
ApiOpt = Annotated[str, typer.Option("--api-url", envvar="ET_API_URL")]


def _render_table(rows: list[tuple[str, ExtractedBill, list]]) -> None:
    table = Table(title="Extracted bills")
    for column in ("File", "Period", "kWh", "Unit price", "Total", "Cur", "Issues"):
        table.add_column(column)
    for filename, bill, issues in rows:
        issue_text = "; ".join(
            f"[red]{i.message}[/red]" if i.level == "error" else f"[yellow]{i.message}[/yellow]"
            for i in issues
        ) or "[green]ok[/green]"
        table.add_row(
            filename,
            f"{bill.period_start} → {bill.period_end}",
            str(bill.consumption_kwh or "—"),
            str(bill.unit_price or "—"),
            str(bill.total_amount),
            bill.currency_code,
            issue_text,
        )
    console.print(table)


def _extract(pdf_dir: Path, cache: Path, expected_currency: str | None):
    client = Anthropic()
    results = extract_directory(client, pdf_dir, cache)
    if not results:
        console.print(f"[yellow]No PDFs found in {pdf_dir}[/yellow]")
        raise typer.Exit(1)
    return [
        (path.name, bill, validate_bill(bill, expected_currency))
        for path, bill in results
    ]


@app.command()
def extract(
    dir: DirOpt,
    cache: CacheOpt = Path("extracted.jsonl"),
    currency: Annotated[
        str | None, typer.Option(help="Expected currency (hard error on mismatch)")
    ] = None,
    dry_run: bool = typer.Option(False, "--dry-run", help="Only print the table"),
) -> None:
    """Extract all PDFs in a directory into the cache file."""
    rows = _extract(dir, cache, currency)
    _render_table(rows)
    if not dry_run:
        console.print(f"Cached to [bold]{cache}[/bold] — review, then run `upload`.")


@app.command()
def upload(
    place_id: PlaceOpt,
    cache: CacheOpt = Path("extracted.jsonl"),
    dir: DirOpt = Path("."),
    api_url: ApiOpt = "http://localhost:8000",
) -> None:
    """Upload previously extracted bills to the API (409 duplicates are skipped)."""
    _upload(place_id, dir, cache, api_url)


@app.command()
def run(
    dir: DirOpt,
    place_id: PlaceOpt,
    cache: CacheOpt = Path("extracted.jsonl"),
    api_url: ApiOpt = "http://localhost:8000",
) -> None:
    """Extract and upload in one go."""
    _upload(place_id, dir, cache, api_url)


def _upload(place_id: str, pdf_dir: Path, cache: Path, api_url: str) -> None:
    api = EnerglensClient(api_url)
    place = api.get_place(place_id)
    console.print(
        f"Uploading to [bold]{place['name']}[/bold] ({place['currency_code']})"
    )

    rows = _extract(pdf_dir, cache, expected_currency=place["currency_code"])
    _render_table(rows)

    errored = [name for name, _, issues in rows if any(i.level == "error" for i in issues)]
    if errored:
        console.print(
            f"[red]Not uploading — fix errors first in: {', '.join(errored)}[/red]"
        )
        raise typer.Exit(1)

    counts = {"created": 0, "skipped": 0}
    for filename, bill, _ in rows:
        outcome = api.create_bill(place_id, to_api_payload(bill, filename))
        counts[outcome] += 1
        marker = "[green]created[/green]" if outcome == "created" else "[dim]skipped (duplicate)[/dim]"
        console.print(f"  {filename}: {marker}")
    console.print(
        f"Done: {counts['created']} created, {counts['skipped']} skipped."
    )


if __name__ == "__main__":
    app()
