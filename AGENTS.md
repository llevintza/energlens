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

## Conventions

- Python is managed with `uv` (`uv sync`, `uv run …`) in `backend/` and `ingest/`.
- Local Postgres without Docker: `scripts/pgdev.sh init` / `start`.
- Tests: `cd backend && uv run pytest`, `cd ingest && uv run pytest`,
  `cd frontend && npx tsc -b`.
- Never commit `.env`, tokens, or credentials.
