"""Pin the Node version that has to be duplicated.

`.nvmrc` is the single source of truth, and most consumers read it directly:
`actions/setup-node` through `node-version-file`, `nvm use` locally. Two cannot:

  frontend/package.json  npm needs a literal range in the manifest; `engines`
                         cannot point at a file outside the package
  README.md              prose, for the human arriving at the repo

This file exists for the failure that was live until #70: `README.md` said Node
20 while both workflows ran 22 and nothing declared `engines` at all. An agent
believed the README, installed 20, and hit a difference CI could not reproduce.

It lives in the backend suite because that is where this repo's other drift pin
lives (`test_config.py`, for the database identity) and because `backend-ci.yml`
carries no paths filter, so it runs on every pull request. Nothing here touches
the database.
"""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

WORKFLOWS = sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml"))


def pinned_major() -> str:
    return (REPO_ROOT / ".nvmrc").read_text().strip()


class TestNodeVersion:
    def test_nvmrc_pins_a_bare_major(self):
        # A bare major resolves to the newest 22.x wherever it is read, which is
        # what keeps CI on a release recent enough for the tighter floors the
        # dependency tree declares (jsdom wants ^22.22.2). A full version here
        # would freeze that and go stale silently.
        text = (REPO_ROOT / ".nvmrc").read_text()
        assert re.fullmatch(r"\d+\n", text), (
            f".nvmrc should hold a bare major and a newline, got {text!r}"
        )

    def test_engines_floor_matches_nvmrc(self):
        major = pinned_major()
        package = json.loads((REPO_ROOT / "frontend" / "package.json").read_text())
        assert package["engines"]["node"] == f">={major}", (
            f"frontend/package.json engines.node disagrees with .nvmrc ({major})"
        )

    def test_npmrc_makes_engines_binding(self):
        # Without engine-strict, npm prints EBADENGINE and installs anyway, and
        # the floor above is decoration rather than a check.
        npmrc = (REPO_ROOT / "frontend" / ".npmrc").read_text()
        assert "engine-strict=true" in npmrc

    def test_readme_names_the_pinned_major(self):
        major = pinned_major()
        assert f"Node {major}+" in (REPO_ROOT / "README.md").read_text(), (
            f"README.md should say Node {major}+, matching .nvmrc"
        )

    def test_agents_md_names_the_pinned_major(self):
        major = pinned_major()
        assert f"pinned at {major}" in (REPO_ROOT / "AGENTS.md").read_text(), (
            f"AGENTS.md should say Node is pinned at {major}, matching .nvmrc"
        )

    def test_no_workflow_hardcodes_a_node_version(self):
        # `node-version-file:` deliberately does not match: the point is that a
        # workflow reads .nvmrc instead of carrying its own copy of the number.
        literal = re.compile(r"^\s*node-version:", re.MULTILINE)
        offenders = [wf.name for wf in WORKFLOWS if literal.search(wf.read_text())]
        assert not offenders, (
            f"{', '.join(offenders)} pins Node inline; use "
            f"`node-version-file: .nvmrc` so there is one copy of the version"
        )
