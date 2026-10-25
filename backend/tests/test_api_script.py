"""`scripts/api.sh smoke` waits for the commit under test, offline.

The smoke itself probes production, so it stays outside `make check` (AGENTS.md).
Its decision logic does not need production: this file serves `/health` and
`/openapi.json` from a local server, runs the real script from a throwaway git
repository, and pins the behaviour issue #91 was filed for — a smoke run ten
seconds after a merge went green against the *previous* revision, because every
field it checked held on both.

Lives in the backend suite for the same reason `test_toolchain.py` does:
`backend-ci.yml` has no paths filter, so it runs on every pull request.
"""

import json
import os
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

OPENAPI = {"info": {"title": "Energlens API"}, "paths": {"/users/me": {"delete": {}}}}

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or shutil.which("curl") is None,
    reason="needs git and curl, which every CI runner has",
)


@pytest.fixture
def api():
    """A stand-in for the deployed API. Tests set `state` to what it serves."""
    state = {"health": {"status": "ok"}, "openapi": OPENAPI}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            doc = {"/health": state["health"], "/openapi.json": state["openapi"]}.get(
                self.path
            )
            payload = json.dumps(doc).encode()
            self.send_response(200 if doc is not None else 404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state["url"] = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "commit.gpgsign=false", *args],
        check=True,
        capture_output=True,
        text=True,
        env=git_env(),
    ).stdout.strip()


def git_env() -> dict[str, str]:
    env = dict(os.environ)
    # Isolated from whoever runs the suite: no signing hooks, no global aliases.
    env.update(
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_AUTHOR_NAME="t",
        GIT_AUTHOR_EMAIL="t@example.com",
        GIT_COMMITTER_NAME="t",
        GIT_COMMITTER_EMAIL="t@example.com",
    )
    return env


@pytest.fixture
def repo(tmp_path):
    """backend/ v1 → backend/ v2 → frontend/ only, with origin/main at the tip.

    The last commit is the rootDir case: Render never deploys it, because it
    changes nothing under backend/, so the smoke must expect `backend_v2`.
    """
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    shutil.copy(REPO_ROOT / "scripts" / "api.sh", root / "scripts" / "api.sh")
    git(root, "init", "-q")
    git(root, "add", "scripts")
    git(root, "commit", "-qm", "script")

    commits = {}
    for name, path in [
        ("backend_v1", "backend/a"),
        ("backend_v2", "backend/a"),
        ("frontend", "frontend/b"),
    ]:
        f = root / path
        f.parent.mkdir(exist_ok=True)
        f.write_text(name)
        git(root, "add", path)
        git(root, "commit", "-qm", name)
        commits[name] = git(root, "rev-parse", "HEAD")
    git(root, "update-ref", "refs/remotes/origin/main", commits["frontend"])
    return root, commits


def run(repo_root: Path, api, cmd: str = "smoke", **env: str):
    environ = git_env()
    for var in ("GITHUB_ACTIONS", "API_URL", "API_EXPECT_COMMIT"):
        environ.pop(var, None)
    # Defaults first, so a test can override any of them.
    environ.update(
        {
            "API_PREFLIGHT_ATTEMPTS": "2",
            "API_PREFLIGHT_INTERVAL": "0",
            "API_PREFLIGHT_CHECK_DB": "0",
            **env,
        }
    )
    return subprocess.run(
        ["sh", str(repo_root / "scripts" / "api.sh"), cmd, api["url"]],
        capture_output=True,
        text=True,
        env=environ,
        timeout=60,
    )


class TestSmokeWaitsForTheCommit:
    def test_passes_when_the_newest_backend_commit_is_live(self, repo, api):
        root, c = repo
        api["health"] = {"status": "ok", "commit": c["backend_v2"]}
        r = run(root, api)
        assert r.returncode == 0, r.stderr
        assert f"serves commit {c['backend_v2']}" in r.stdout
        # Not origin/main's tip: that commit only touched frontend/, and Render
        # (rootDir: backend) never deploys it. Waiting for it would time out.
        assert f"waiting for commit {c['backend_v2']}" in r.stdout

    def test_passes_when_a_later_commit_is_already_live(self, repo, api):
        """A later merge deploying first is a current API, not a stale one."""
        root, c = repo
        api["health"] = {"status": "ok", "commit": c["backend_v2"]}
        r = run(root, api, API_EXPECT_COMMIT=c["backend_v1"])
        assert r.returncode == 0, r.stderr

    def test_accepts_a_short_sha(self, repo, api):
        root, c = repo
        api["health"] = {"status": "ok", "commit": c["backend_v2"][:7]}
        r = run(root, api)
        assert r.returncode == 0, r.stderr

    def test_fails_as_stale_when_the_previous_revision_answers(self, repo, api):
        """Issue #91 itself: up, OpenAPI contract intact, one merge behind."""
        root, c = repo
        api["health"] = {"status": "ok", "commit": c["backend_v1"]}
        r = run(root, api)
        assert r.returncode == 1
        assert "Deploy is stale" in r.stderr
        assert c["backend_v1"] in r.stderr and c["backend_v2"] in r.stderr
        assert "openapi ok" not in r.stdout, (
            "must not pass the contract on a stale commit"
        )

    def test_fails_as_stale_when_health_names_no_commit(self, repo, api):
        """What production serves today (#97): a revision from before the field."""
        root, _ = repo
        api["health"] = {"status": "ok"}
        r = run(root, api)
        assert r.returncode == 1
        assert "Deploy is stale" in r.stderr
        assert "names no commit" in r.stderr

    @pytest.mark.parametrize("served", ["unknown", "main", "HEAD"])
    def test_a_non_sha_is_never_live(self, repo, api, served):
        """'main' and 'HEAD' resolve in git; they must not pass as a deploy."""
        root, _ = repo
        api["health"] = {"status": "ok", "commit": served}
        r = run(root, api)
        assert r.returncode == 1
        assert "Deploy is stale" in r.stderr

    def test_a_broken_contract_on_the_right_commit_is_not_called_stale(self, repo, api):
        root, c = repo
        api["health"] = {"status": "ok", "commit": c["backend_v2"]}
        api["openapi"] = {"info": {"title": "Energlens API"}, "paths": {}}
        r = run(root, api)
        assert r.returncode == 1
        assert "Deploy is stale" not in r.stderr
        assert "OpenAPI contract does not hold" in r.stderr

    def test_a_broken_contract_on_the_right_commit_fails_fast(self, repo, api):
        """The commit is proven live, so waiting out the deploy budget is pointless."""
        root, c = repo
        api["health"] = {"status": "ok", "commit": c["backend_v2"]}
        api["openapi"] = {"info": {"title": "Energlens API"}, "paths": {}}
        r = run(root, api, API_PREFLIGHT_ATTEMPTS="5")
        assert r.returncode == 1
        assert "attempt 1/5" in r.stderr
        assert "attempt 2/5" not in r.stderr
        assert "does not hold after 2 attempts" in r.stderr

    def test_fails_clearly_without_a_commit_to_expect(self, repo, api):
        root, c = repo
        git(root, "update-ref", "-d", "refs/remotes/origin/main")
        api["health"] = {"status": "ok", "commit": c["backend_v2"]}
        r = run(root, api)
        assert r.returncode == 1
        assert "fetch-depth: 0" in r.stderr


class TestPreflightAcceptsBothHealthBodies:
    """Preflight gates frontend deploys and must not care which revision is up."""

    @pytest.mark.parametrize(
        "health", [{"status": "ok"}, {"status": "ok", "commit": "0123abc"}]
    )
    def test_ok(self, repo, api, health):
        root, _ = repo
        api["health"] = health
        r = run(root, api, "preflight")
        assert r.returncode == 0, r.stderr

    def test_still_rejects_another_status(self, repo, api):
        root, _ = repo
        api["health"] = {"status": "okay", "commit": "0123abc"}
        r = run(root, api, "preflight")
        assert r.returncode == 1
