# 0009. Use `uv` for Python dependency management

- **Status:** Accepted
- **Date:** 2026-08-10
- **Deciders:** llevintza
- **Landed in:** PR #1 (`81b373b`)
- **Related:** [ADR-0002](0002-monorepo-with-make-as-command-surface.md), [ADR-0011](0011-backend-hosting-render.md)

## Context

Two independent Python packages live in this repo — `backend/` and `ingest/` — with
different dependency sets. Both need reproducible installs locally, in CI, and on
Render, where build minutes are limited and cold builds happen on every deploy.

## Decision

**`uv`** for both packages, each with its own `pyproject.toml` and `uv.lock`, driven
through `make` targets rather than invoked directly
([ADR-0002](0002-monorepo-with-make-as-command-surface.md)).

Render installs with **`uv sync --locked`**, and the flag choice is deliberate:

| Flag | Behaviour | Why not |
| --- | --- | --- |
| `--frozen` | Installs the lock without checking it matches `pyproject.toml` | Turns lockfile drift into a `ModuleNotFoundError` **crash-loop at runtime** |
| `--locked` | Fails if the lock is stale | Turns the same drift into a **build-time error** — chosen |

`make lock-check` runs `uv lock --check` in both packages as part of the merge gate,
so drift is caught in CI before it can reach a deploy at all.

## Consequences

### What this buys

- **Fast installs** — meaningfully so on Render, where every deploy is a cold build.
- **Reproducible environments** from a committed lockfile, in all three places.
- One tool for virtualenv creation, dependency resolution, locking and running
  (`uv run`), replacing pip + venv + pip-tools.
- Two isolated packages in one repo without a workspace tool.

### What this costs

- **A newer tool with a smaller install base** than pip. It must be present on the
  build host; `render.yaml` handles that with `pip install uv` as the first step of
  the build command.
- `uv.lock` is uv-specific — not `requirements.txt`, not PEP 751. Another tool cannot
  read it.
- Two lockfiles to keep current, which is why `lock-check` covers both.
- Rapid release cadence; behaviour has changed across versions.

## Limitations

- Not usable for the frontend — npm remains for `frontend/`, so the repo has two
  package managers regardless.
- No workspace/monorepo mode in use here; the two packages are independent, which is
  simple but means shared code would have to be published or path-installed.
- `uv` must exist on any new build host.

## Alternatives considered

| Option | Why not |
| --- | --- |
| **pip + `requirements.txt`** | Universally available, but no real lockfile without pip-tools, and materially slower cold installs |
| **Poetry** | Mature and well understood; slower, and its lockfile has historically been a source of CI churn |
| **PDM** | Standards-forward, smaller community, no decisive advantage over uv here |
| **Pipenv** | Slow resolution and a lock format with a poor reliability reputation |
| **Conda** | Aimed at scientific binary distribution; heavyweight and unnecessary |

## Revisit when

- [ ] **A build host cannot install `uv`** → `uv export` produces a `requirements.txt`
      as an escape hatch.
- [ ] **PEP 751 (`pylock.toml`) is widely supported** → a standard lockfile would
      remove the tool-specific format concern.
- [ ] **`backend/` and `ingest/` need to share code** → uv workspaces, or extract a
      third package.
- [ ] **uv makes a breaking change** that costs more than it saves.

## Migration path

Escaping is cheap: `uv export --format requirements-txt > requirements.txt` per
package, then `pip install -r`. The `pyproject.toml` files are standard and readable
by any modern tool — only the lockfile format is uv-specific, and it is regenerable
rather than authored.
