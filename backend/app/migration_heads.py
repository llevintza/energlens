"""Refuse to run with more than one Alembic head, and say how to fix it.

Two branches that each add a migration on the same parent both pass CI on
their own, and after both merge, ``main`` has two heads. ``start.sh`` runs
``alembic upgrade head`` on every Render boot, so the next deploy does not fail
a step: the API stops starting. Alembic's own error ("Multiple head revisions
are present for given argument 'head'") names the symptom, not the fix.

This check needs no database — it only reads ``alembic/versions/`` — so it runs
first in ``make check`` (``make migrate-heads``), in the backend suite, and from
``alembic/env.py``, which puts the same explanation in front of CI's migration
step and in the Render boot log. See ``docs/migrations.md``.

    uv run python -m app.migration_heads
"""

import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).resolve().parents[1]


def script_directory() -> ScriptDirectory:
    # Pinned to an absolute path: alembic.ini's `script_location = alembic` is
    # relative to the working directory, and pytest or make may run elsewhere.
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return ScriptDirectory.from_config(config)


def heads_problem(script: ScriptDirectory) -> str | None:
    """The explanation to print when there is not exactly one head, else None."""
    heads = sorted(script.get_revisions("heads"), key=lambda r: r.revision)
    if len(heads) == 1:
        return None
    if not heads:
        return "No Alembic revisions found in alembic/versions/ — expected exactly one head."

    lines = [
        f"Alembic has {len(heads)} heads; it must have exactly one.",
        "",
        "Production runs `alembic upgrade head` on every boot (backend/start.sh),",
        "so this would stop the API from starting rather than fail a deploy step.",
        "It happens when two branches each add a migration on the same parent.",
        "",
    ]
    for rev in heads:
        lines.append(
            f"  {rev.revision}  down_revision={rev.down_revision!r}  "
            f"alembic/versions/{Path(rev.path).name}"
        )
    lines += [
        "",
        "Fix: take the head your branch added (if both are on main already, the",
        "one merged last — no boot got past this, so it was never applied) and",
        "set its `down_revision`, and the `Revises:` line in its docstring, to the",
        "other head's revision ID. Then run `make migrate-check` to prove the",
        "chain applies and still matches the models. Never edit a migration that",
        "production has applied. See docs/migrations.md.",
    ]
    return "\n".join(lines)


def main() -> int:
    script = script_directory()
    if problem := heads_problem(script):
        print(problem, file=sys.stderr)
        return 1
    print(f"one Alembic head: {script.get_current_head()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
