# Energlens — agent instructions

Electricity bill tracker. FastAPI + PostgreSQL backend, React/Vite SPA frontend,
and an `energlens-ingest` CLI that extracts bill PDFs with Claude. See
`README.md` for the layout and local setup.

## Environment

This repo uses `direnv`. `.envrc` is committed and holds no secrets; it loads
your gitignored `.env` and exports it, so anything you run from this directory
inherits the same variables. After cloning:

```sh
gh auth login                # or put a PAT in .env — see below
cp .env.example .env
direnv allow
```

Authenticate *before* `direnv allow`: `.envrc` reads the `gh` keyring at the
moment it evaluates, so logging in afterwards leaves the exported token empty
until you `direnv reload` or open a new shell. Editing `.env` reloads on its
own — direnv watches that file.

Without `direnv`, reproduce both halves before launching a harness. Sourcing
`.env` alone exports the blank placeholder and skips the keyring fallback:

```sh
set -a; . ./.env; set +a
: "${GITHUB_MCP_PAT:=$(gh auth token 2>/dev/null)}"; export GITHUB_MCP_PAT
```

## GitHub MCP server

The `github` MCP server is configured at project scope for every harness, and
authenticates with a **per-contributor** GitHub token read from the
`GITHUB_MCP_PAT` environment variable. No token is committed — the config files
reference the variable name only.

| Harness | Committed config |
| --- | --- |
| Claude Code | `.mcp.json` |
| Copilot CLI | `.mcp.json` |
| Cursor | `.cursor/mcp.json` (note: `${env:VAR}` syntax) |
| Gemini CLI | `.gemini/settings.json` |
| Codex | `.codex/config.toml` (trusted projects only) |
| Muse Code | user-level only — see `README.md` |

**If the `github` MCP tools are missing or the server reports 401/failed, the
cause is almost always an unset `GITHUB_MCP_PAT`.** To repair:

1. In a fresh clone, `direnv allow` — the `.envrc` guard names the problem on
   entering the directory.
2. `gh auth login`, **then `direnv reload`** — `.envrc` already read the keyring,
   and authenticating does not re-trigger it on its own.
3. Or mint a PAT (see below) and set `GITHUB_MCP_PAT` in `.env`; that path needs
   no reload, because direnv watches `.env`.

Do not work around a missing token by putting a literal token in any committed
file, and do not add the token to `.claude/settings.local.json` or another
harness-specific settings file — that fixes one harness and silently leaves the
rest broken.

Token permissions, minted at <https://github.com/settings/personal-access-tokens>:
a fine-grained PAT needs **Contents: Read and write**, plus **Workflows: Read and
write** to edit files under `.github/workflows/`. On a classic PAT those are the
`repo` and `workflow` scopes — `workflow` is classic-only and is not offered in
the fine-grained UI. `gh auth token` returns the *active* account's token, which
carries classic scopes.

## Commands

Everything runs through `make` from the repo root. Use it rather than raw `uv`,
`npm` or `alembic`: the targets know the working directories, and the database
ones run a preflight that explains failures instead of raising
`ConnectionRefusedError`.

| Task | Command |
| --- | --- |
| Set up a clone | `make setup` |
| Start Postgres | `make db-up` |
| **The gate — run before calling anything done** | `make check` |
| One backend test | `make test-backend PYTEST_ARGS="-k currency"` |
| New migration | `make migration m="add reference to bill"` |
| Reset the database | `make db-reset` (drops both databases) |
| Run the app | `make dev-api`, `make dev-web` |
| Everything else | `make help` |

`make check` is exactly what the merge-gating CI jobs run, so the two cannot
disagree. `deploy-frontend.yml` is not part of it — that is a deploy, not a
gate, and it depends on production-only repository variables.

## Conventions

- Python is managed with `uv` in `backend/` and `ingest/`; the `make` targets
  wrap it. Node is pinned by CI at 22.
- Database identity — user, port, both database names — is defined in
  `scripts/db.env`. `scripts/db.sh` and `scripts/pgdev.sh` source it; the
  environment overrides it, so `PGPORT=5433 make db-up` works. Four consumers
  cannot read it when they need it and so keep literal copies —
  `backend/app/config.py`, the CI service block, `docker-compose.yml` and
  `.env.example`. **`backend/tests/test_config.py` fails if any copy drifts**,
  so change `db.env` and let the test tell you what else to update.
- The test suite drops every table in `energlens_test` on each run. That is why
  the preflight refuses to run when `DATABASE_URL` points off localhost.
- Never commit `.env`, tokens, credentials, real bill PDFs, or
  `.claude/settings.local.json`.
