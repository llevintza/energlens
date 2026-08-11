# Energlens — agent instructions

Electricity bill tracker. FastAPI + PostgreSQL backend, React/Vite SPA frontend,
and an `energlens-ingest` CLI that extracts bill PDFs with Claude. See
`README.md` for the layout and local setup.

## Environment

This repo uses `direnv`. `.envrc` is committed and holds no secrets; it loads
your gitignored `.env` and exports it, so anything you run from this directory
inherits the same variables. After cloning:

```sh
cp .env.example .env
direnv allow
```

Without `direnv`, run `set -a; . ./.env; set +a` before launching a harness.

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

1. `direnv allow` — the `.envrc` guard prints the problem on entering the directory.
2. `gh auth login` — `.envrc` falls back to the `gh` CLI keyring automatically.
3. Or mint a fine-grained PAT at
   <https://github.com/settings/personal-access-tokens> and set
   `GITHUB_MCP_PAT` in `.env`.

Do not work around a missing token by putting a literal token in any committed
file, and do not add the token to `.claude/settings.local.json` or another
harness-specific settings file — that fixes one harness and silently leaves the
rest broken.

Note: `gh auth token` returns the *active* account's token. Editing files under
`.github/workflows/` through the MCP server needs a token with the `workflow`
scope.

## Conventions

- Python is managed with `uv` (`uv sync`, `uv run …`) in `backend/` and `ingest/`.
- Local Postgres without Docker: `scripts/pgdev.sh init` / `start`.
- Tests: `cd backend && uv run pytest`, `cd ingest && uv run pytest`,
  `cd frontend && npx tsc -b`.
- Never commit `.env`, tokens, or credentials.
