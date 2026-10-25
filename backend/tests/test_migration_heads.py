"""The single-head rule for Alembic, checked without a database.

`start.sh` runs `alembic upgrade head` on every boot, so two heads on main is an
outage, not a failed test. Two branches that each add a migration on the same
parent produce exactly that, and each passes CI on its own. See
`docs/migrations.md`.
"""

import subprocess
import sys
from pathlib import Path

from alembic.script import ScriptDirectory

from app.migration_heads import BACKEND_DIR, heads_problem, script_directory

REVISION = '''"""{message}

Revision ID: {revision}
Revises: {down}
"""
revision = {revision!r}
down_revision = {down!r}
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
'''


def make_script(tmp_path: Path, chain: dict[str, str | None]) -> ScriptDirectory:
    versions = tmp_path / "versions"
    versions.mkdir()
    for revision, down in chain.items():
        (versions / f"{revision}_test.py").write_text(
            REVISION.format(message=revision, revision=revision, down=down)
        )
    return ScriptDirectory(str(tmp_path))


def test_the_repository_has_exactly_one_head():
    # The real chain. If this fails, the message says which file to repoint.
    problem = heads_problem(script_directory())
    assert problem is None, problem


def test_a_linear_chain_passes(tmp_path):
    script = make_script(tmp_path, {"aaa": None, "bbb": "aaa", "ccc": "bbb"})
    assert heads_problem(script) is None


def test_two_migrations_on_one_parent_explain_the_fix(tmp_path):
    # The case this check exists for: two PRs, each adding one revision on main.
    script = make_script(tmp_path, {"aaa": None, "bbb": "aaa", "ccc": "aaa"})
    problem = heads_problem(script)

    assert problem is not None
    assert "2 heads" in problem
    # Names both heads, their shared parent and their files, so the author can
    # see which one is theirs without running alembic.
    assert "bbb  down_revision='aaa'  alembic/versions/bbb_test.py" in problem
    assert "ccc  down_revision='aaa'  alembic/versions/ccc_test.py" in problem
    # And says what to do about it, not just that it is wrong.
    assert "set its `down_revision`" in problem
    assert "make migrate-check" in problem
    assert "docs/migrations.md" in problem


def test_the_command_line_entry_point_succeeds_on_the_real_chain():
    # What `make migrate-heads` runs. Run from elsewhere on purpose: the
    # script location must not depend on the working directory.
    result = subprocess.run(
        [sys.executable, "-m", "app.migration_heads"],
        cwd=BACKEND_DIR.parent,
        env={"PYTHONPATH": str(BACKEND_DIR)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("one Alembic head: ")


def test_env_py_runs_the_check_before_resolving_head():
    # Without this, CI's `alembic upgrade head` step and the Render boot log
    # show Alembic's own message, which names the symptom and not the fix.
    env_py = (BACKEND_DIR / "alembic" / "env.py").read_text()
    assert "heads_problem(context.script)" in env_py
