"""Pin the instruction pointers that send each harness to AGENTS.md.

`AGENTS.md` is the single source of truth for agent instructions. Harnesses
that do not read it natively get a stub that only points at it:

  CLAUDE.md                        Claude Code, through `@AGENTS.md`
  .github/copilot-instructions.md  Copilot
  .cursor/rules/agents.mdc         Cursor, with `alwaysApply: true`
  .gemini/settings.json            Gemini CLI, through `context.fileName`

A stub that is deleted or renamed fails silently: the harness runs without the
repo's rules and nothing errors. This file turns that into a red test. Like
`test_toolchain.py`, it lives in the backend suite because `backend-ci.yml` runs
on every pull request, and it never touches the database.
"""

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Each stub and the text it must contain. Claude Code imports a file only
# through `@path`, so a plain mention of AGENTS.md in CLAUDE.md would load nothing.
STUBS = {
    "CLAUDE.md": "@AGENTS.md",
    ".github/copilot-instructions.md": "AGENTS.md",
    ".cursor/rules/agents.mdc": "AGENTS.md",
}


@pytest.mark.parametrize(("stub", "pointer"), STUBS.items())
def test_stub_points_at_agents_md(stub, pointer):
    path = REPO_ROOT / stub
    assert path.is_file(), f"{stub} is missing; its harness would skip AGENTS.md"
    assert pointer in path.read_text(), (
        f"{stub} should point at AGENTS.md with {pointer}"
    )


def test_cursor_rule_always_applies():
    # Without alwaysApply, Cursor attaches the rule only when its description or
    # globs match, so most chats would never see the pointer.
    text = (REPO_ROOT / ".cursor" / "rules" / "agents.mdc").read_text()
    assert text.startswith("---"), "agents.mdc should open with a --- frontmatter block"
    frontmatter = text.split("---")[1]
    assert "alwaysApply: true" in frontmatter.splitlines()


def test_gemini_loads_agents_md():
    settings = json.loads((REPO_ROOT / ".gemini" / "settings.json").read_text())
    names = settings["context"]["fileName"]
    if isinstance(names, str):
        names = [names]
    assert "AGENTS.md" in names, (
        ".gemini/settings.json context.fileName lacks AGENTS.md"
    )


def test_no_gemini_md_beside_agents_md():
    # context.fileName keeps GEMINI.md so Gemini still loads the user's own
    # ~/.gemini/GEMINI.md, but a committed one would be a second source of truth.
    assert not (REPO_ROOT / "GEMINI.md").exists(), (
        "GEMINI.md would compete with AGENTS.md; put the rules in AGENTS.md instead"
    )
