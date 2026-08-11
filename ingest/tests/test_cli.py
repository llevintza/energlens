"""Smoke tests for the wiring the model tests can't see.

test_models.py only imports models.py, so a broken import or a stale entry
point in cli.py / api_client.py passes CI and fails on the user's first run.
"""

from importlib.metadata import entry_points
from pathlib import Path

import pytest
from typer.testing import CliRunner

from energlens_ingest.api_client import ApiError, EnerglensClient
from energlens_ingest.cli import app

runner = CliRunner()


def test_entry_point_resolves_to_the_cli():
    (script,) = [
        ep for ep in entry_points(group="console_scripts") if ep.name == "energlens-ingest"
    ]
    assert script.load() is app


def test_help_lists_every_command():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("extract", "upload", "run"):
        assert command in result.stdout


def test_upload_without_a_cache_file_exits_before_touching_the_api(tmp_path):
    """`upload` must read the cache, not re-extract (which needed an API key)."""
    result = runner.invoke(
        app,
        ["upload", "--place-id", "abc", "--cache", str(tmp_path / "missing.jsonl")],
    )
    assert result.exit_code == 1


def test_dry_run_extract_makes_no_api_calls(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (tmp_path / "bill.pdf").write_bytes(b"%PDF-1.4 not really a pdf")

    result = runner.invoke(
        app,
        ["extract", "--dir", str(tmp_path), "--cache", str(tmp_path / "c.jsonl"), "--dry-run"],
    )

    assert result.exit_code == 0
    assert not (tmp_path / "c.jsonl").exists()


def test_env_credentials_accept_both_namespaces(monkeypatch):
    monkeypatch.delenv("ENERGLENS_TOKEN", raising=False)
    monkeypatch.setenv("ET_TOKEN", "legacy-token")
    assert EnerglensClient("http://localhost:8000")._token == "legacy-token"

    monkeypatch.setenv("ENERGLENS_TOKEN", "current-token")
    assert EnerglensClient("http://localhost:8000")._token == "current-token"


def test_login_without_credentials_names_the_current_env_vars(monkeypatch):
    for name in ("ENERGLENS_TOKEN", "ENERGLENS_EMAIL", "ENERGLENS_PASSWORD",
                 "ET_TOKEN", "ET_EMAIL", "ET_PASSWORD"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ApiError, match="ENERGLENS_EMAIL"):
        EnerglensClient("http://localhost:8000").login()


def test_cache_loader_round_trips(tmp_path):
    from energlens_ingest.claude_extractor import load_cached_bills

    cache = Path(tmp_path / "cache.jsonl")
    cache.write_text(
        '{"sha256": "deadbeef", "file": "jan.pdf", "bill": {'
        '"period_start": "2025-01-01", "period_end": "2025-01-31", '
        '"consumption_kwh": "310.5", "total_amount": "72.40", '
        '"currency_code": "EUR"}}\n'
    )

    (path, bill), = load_cached_bills(cache)
    assert path.name == "jan.pdf"
    assert bill.currency_code == "EUR"
