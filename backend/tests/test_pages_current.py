"""Exercise scripts/pages-current.sh offline, against a stubbed `gh`.

The script exists because a push to main once produced no workflow run at all
(issue #95), and the deploy's own alert lives inside the run that never
happened. It only ever runs on a schedule against the real API, so a logic slip
— alerting on every backend-only merge, or never alerting — would otherwise
first show up in production, as noise or as silence.

The stub answers `gh api <path> --jq <filter>` from canned JSON through the real
`jq`, so the filters the script sends are exercised as written. Nothing here
touches the network or the database. It lives in the backend suite for the same
reason test_toolchain.py does: backend-ci.yml has no paths filter.
"""

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "pages-current.sh"
REPO = "owner/repo"

STUB_GH = r"""#!/bin/sh
# gh api <path> --jq <filter>, answered from $FIXTURES; a missing fixture is an
# API failure.
[ "$1" = api ] && [ "$3" = --jq ] || { echo "stub gh: unexpected call: $*" >&2; exit 2; }
file="$FIXTURES/$(printf '%s' "$2" | tr -c 'A-Za-z0-9' '_').json"
[ -f "$file" ] || { echo "stub gh: no fixture for $2" >&2; exit 1; }
exec jq -r "$4" "$file"
"""

DEPLOYED = "d" * 40
OLDER = "c" * 40


def sha(n: int) -> str:
    return f"{n:040x}"


def iso(seconds_ago: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - seconds_ago))


@pytest.fixture
def gh(tmp_path):
    if shutil.which("jq") is None:
        pytest.fail("these tests need jq on PATH (brew install jq)")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "gh"
    stub.write_text(STUB_GH)
    stub.chmod(0o755)
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()

    def respond(path: str, body) -> None:
        name = re.sub(r"[^A-Za-z0-9]", "_", f"repos/{REPO}/{path}")
        (fixtures / f"{name}.json").write_text(json.dumps(body))

    def run(**env):
        result = subprocess.run(
            ["sh", str(SCRIPT)],
            capture_output=True,
            text=True,
            check=False,
            env={
                "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                "FIXTURES": str(fixtures),
                "GITHUB_REPOSITORY": REPO,
                **env,
            },
        )
        return result.returncode, result.stderr

    respond.run = run
    return respond


def deployments(gh, *pairs) -> None:
    """(sha, latest status) per deployment, newest first."""
    gh(
        "deployments?environment=github-pages&per_page=30",
        [{"id": i, "sha": s} for i, (s, _) in enumerate(pairs, start=1)],
    )
    for i, (_, state) in enumerate(pairs, start=1):
        gh(f"deployments/{i}/statuses?per_page=1", [{"state": state}])


def compare(gh, base: str, status: str, commits, ahead_by=None) -> None:
    """commits: (sha, seconds ago) on main past `base`, oldest first."""
    gh(
        f"compare/{base}...main",
        {
            "status": status,
            "ahead_by": len(commits) if ahead_by is None else ahead_by,
            "commits": [
                {"sha": s, "commit": {"committer": {"date": iso(ago)}}}
                for s, ago in commits
            ],
        },
    )


def touching(gh, per_page: int, frontend=(), workflow=()) -> None:
    gh(
        f"commits?sha=main&path=frontend&per_page={per_page}",
        [{"sha": s} for s in frontend],
    )
    gh(
        f"commits?sha=main&path=.github/workflows/deploy-frontend.yml&per_page={per_page}",
        [{"sha": s} for s in workflow],
    )


class TestCurrent:
    def test_deployment_at_head_passes(self, gh):
        deployments(gh, (DEPLOYED, "success"))
        compare(gh, DEPLOYED, "identical", [])
        code, err = gh.run()
        assert code == 0, err
        assert "is main's HEAD" in err

    def test_backend_only_commits_ahead_pass(self, gh):
        # The paths filter means these were never meant to deploy. Comparing
        # HEAD alone would alert on every one of them.
        deployments(gh, (DEPLOYED, "success"))
        compare(gh, DEPLOYED, "ahead", [(sha(1), 7200), (sha(2), 3600)])
        touching(gh, 2, frontend=[OLDER])
        code, err = gh.run()
        assert code == 0, err
        assert "none of them touching" in err

    def test_undeployed_frontend_commit_past_grace_fails(self, gh):
        # Issue #95: the commit landed, no run was created, the site stayed put.
        deployments(gh, (DEPLOYED, "success"))
        compare(gh, DEPLOYED, "ahead", [(sha(1), 7200), (sha(2), 5400), (sha(3), 600)])
        touching(gh, 3, frontend=[sha(3), sha(2), OLDER])
        code, err = gh.run()
        assert code == 1
        assert "behind main" in err
        # Names the oldest, which is the one that has waited longest.
        assert sha(2) in err and "2 commit(s)" in err
        assert 'gh workflow run "Deploy frontend to GitHub Pages"' in err

    def test_workflow_file_change_counts(self, gh):
        deployments(gh, (DEPLOYED, "success"))
        compare(gh, DEPLOYED, "ahead", [(sha(1), 7200)])
        touching(gh, 1, workflow=[sha(1)])
        code, err = gh.run()
        assert code == 1
        assert sha(1) in err

    def test_undeployed_commit_within_grace_passes(self, gh):
        # A deploy is probably running right now.
        deployments(gh, (DEPLOYED, "success"))
        compare(gh, DEPLOYED, "ahead", [(sha(1), 300)])
        touching(gh, 1, frontend=[sha(1)])
        code, err = gh.run()
        assert code == 0, err
        assert "within the 30 min grace" in err

    def test_grace_is_configurable(self, gh):
        deployments(gh, (DEPLOYED, "success"))
        compare(gh, DEPLOYED, "ahead", [(sha(1), 300)])
        touching(gh, 1, frontend=[sha(1)])
        code, _ = gh.run(GRACE_MINUTES="2")
        assert code == 1

    def test_in_flight_and_failed_deployments_are_not_live(self, gh):
        deployments(
            gh, (sha(9), "in_progress"), (sha(8), "failure"), (DEPLOYED, "success")
        )
        compare(gh, DEPLOYED, "identical", [])
        code, err = gh.run()
        assert code == 0, err
        assert f"live deployment is {DEPLOYED}" in err

    def test_no_successful_deployment_fails(self, gh):
        deployments(gh, (sha(9), "failure"))
        code, err = gh.run()
        assert code == 1
        assert "no successful github-pages deployment" in err

    @pytest.mark.parametrize("status", ["diverged", "behind"])
    def test_deployment_not_on_main_fails(self, gh, status):
        deployments(gh, (DEPLOYED, "success"))
        compare(gh, DEPLOYED, status, [])
        code, err = gh.run()
        assert code == 1
        assert f"compare: {status}" in err

    def test_too_far_behind_to_list_fails(self, gh):
        deployments(gh, (DEPLOYED, "success"))
        compare(gh, DEPLOYED, "ahead", [(sha(1), 7200)], ahead_by=300)
        code, err = gh.run()
        assert code == 1
        assert "300 commits behind" in err

    def test_api_failure_fails_loudly(self, gh):
        # No fixtures at all: every call fails. Silence here would be a green.
        code, err = gh.run()
        assert code == 1
        assert "deployments: read" in err

    def test_rejects_a_non_numeric_grace(self, gh):
        code, err = gh.run(GRACE_MINUTES="soon")
        assert code == 1
        assert "GRACE_MINUTES" in err


class TestPinnedToTheDeployWorkflow:
    """The script copies deploy-frontend.yml's push filter; fail if they drift."""

    def deploy_push_filter(self) -> tuple[list[str], list[str]]:
        text = (REPO_ROOT / ".github" / "workflows" / "deploy-frontend.yml").read_text()
        branches = re.search(r"^\s+branches:\s*\[([^\]]*)\]", text, re.MULTILINE)
        paths = re.search(r"^\s+paths:\s*\[([^\]]*)\]", text, re.MULTILINE)
        assert branches and paths, "deploy-frontend.yml's push filter changed shape"

        def items(m):
            return [s.strip().strip("\"'") for s in m.group(1).split(",")]

        return items(branches), items(paths)

    def script_value(self, name: str) -> str:
        m = re.search(rf'^{name}="?([^"\n]*)"?$', SCRIPT.read_text(), re.MULTILINE)
        assert m, f"{name}= not found in {SCRIPT.name}"
        return m.group(1)

    def test_branch_matches(self):
        branches, _ = self.deploy_push_filter()
        assert branches == [self.script_value("BRANCH")]

    def test_paths_match(self):
        _, paths = self.deploy_push_filter()
        # The commits API takes a directory where the workflow takes a glob.
        expected = [p.removesuffix("/**") for p in paths]
        assert self.script_value("DEPLOY_PATHS").split() == expected, (
            "scripts/pages-current.sh DEPLOY_PATHS disagrees with the paths filter "
            "in deploy-frontend.yml"
        )
