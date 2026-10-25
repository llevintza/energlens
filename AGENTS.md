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
| Copilot CLI | `.mcp.json` (trusted folders only) |
| Cursor | `.cursor/mcp.json` (note: `${env:VAR}` syntax) |
| Gemini CLI | `.gemini/settings.json` |
| Codex | `.codex/config.toml` (trusted projects only) |
| Muse Code | user-level only — see `README.md` |

**Copilot CLI expands `${GITHUB_MCP_PAT}` in `.mcp.json` headers**, so the
shared file works for it as-is and needs no `~/.copilot/mcp-config.json`
fallback. Verified on 2026-10-24 with Copilot CLI 1.0.103 by pointing header
variants at a local server that logged what arrived: `${VAR}` and `$VAR` were
sent expanded, but `${env:VAR}` was sent literally, so do not copy Cursor's
syntax into `.mcp.json`. Because bare `$VAR` expands too, a literal `$` in a
header value gets mangled — keep values in the environment, not in the file.
Copilot loads `.mcp.json` only from a folder it trusts: accept the trust prompt
in an interactive session, or pass `--trust-folder` with `copilot -p`. In that
same 1.0.103 test, an untrusted folder's `github` server was skipped silently,
which looks like missing tools, not a 401 — re-check after upgrading Copilot.

**Trusting a folder is a security decision, not a convenience.** Copilot
expands *any* environment variable named in a trusted folder's `.mcp.json`
headers and sends it to whatever `url` the file names, so a repository you
trust can ship your cloud keys or tokens to its own host. Read `.mcp.json` —
every `url` and every variable in its headers — before trusting a folder.

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
| Check migrations match the models | `make migrate-check` |
| Check for one Alembic head (no DB) — protocol in [`docs/migrations.md`](docs/migrations.md) | `make migrate-heads` |
| Reset the database | `make db-reset` (drops both databases) |
| Run the app | `make dev-api`, `make dev-web` |
| Check the deployed API answers | `make api-preflight` |
| Check the deployed API's OpenAPI contract | `make api-smoke` |
| Check the deployed site loads | `make smoke-web` |
| Everything else | `make help` |

`make check` is exactly what the merge-gating CI jobs run, so the two cannot
disagree. `deploy-frontend.yml` is not part of it — that is a deploy, not a
gate, and it depends on production-only repository variables. Neither is
`make api-preflight` or `make api-smoke`, for the same reason: they probe a live
production host, and a gate that depends on Render's uptime blocks merges when
Render is down. Nor is `make smoke-web`: it fetches the *live* site, which tells
you nothing about the branch in front of you.

## Conventions

- Python is managed with `uv` in `backend/` and `ingest/`; the `make` targets
  wrap it.
- Node is pinned at 24 by `.nvmrc` — `actions/setup-node` reads it through
  `node-version-file`, `nvm use` reads it locally. Two consumers cannot read it
  and so keep literal copies: `engines` in `frontend/package.json` (enforced
  rather than advisory, because `frontend/.npmrc` sets `engine-strict=true`, so
  `npm ci` fails instead of warning) and `README.md`.
  **`backend/tests/test_toolchain.py` fails if either copy drifts.**
- Database identity — user, port, all three database names — is defined in
  `scripts/db.env`. `scripts/db.sh` and `scripts/pgdev.sh` source it; the
  environment overrides it, so `PGPORT=5433 make db-up` works. Four consumers
  cannot read it when they need it and so keep literal copies —
  `backend/app/config.py`, the CI service block, `docker-compose.yml` and
  `.env.example`. **`backend/tests/test_config.py` fails if any copy drifts**,
  so change `db.env` and let the test tell you what else to update.
- Three databases: `energlens` (yours), `energlens_test` (every table dropped on
  each test run), and `energlens_migrations` (throwaway, rebuilt by Alembic
  alone for `make migrate-check` — checking migrations against the test database
  would compare the models with themselves and never see drift).
- Because two of those are destroyed routinely, `scripts/db.sh` and
  `conftest.py` both refuse to run when the target host is not localhost —
  whether that host comes from `PGHOST` or from `DATABASE_URL`.
- Never commit `.env`, tokens, credentials, real bill PDFs, or
  `.claude/settings.local.json`.

## Agent roles and PR workflow

Work is split across agents with fixed roles, so that the agent who wrote a
change is never the one who approves it:

- **Orchestrator** — the agent the user talks to. It plans the work, splits it
  into self-contained tasks, dispatches them to Orca orchestration workers
  (`orca orchestration worker-start`) and aggregates their results. It does not
  edit repo files itself; that keeps its context free for coordination.
- **Implementer** (worker) — one task, one branch, one PR. `make check` passes
  before the PR is opened, for the same reason it gates merges.
- **PR Reviewer** (worker) — monitors each open PR until it is merged. It reads
  every comment, inline thread and CI check, and addresses feedback from the
  Tech Coordinator, Leo or anyone else with new commits on the same branch —
  never a force-push, which would hide what changed from the reviewers. It
  replies to each thread saying what changed or why not, resolves the threads
  it addressed, and fixes failing checks. When feedback is ambiguous or
  conflicts with this file, it escalates to the Orchestrator instead of
  guessing.
- **Arbiter** (approver persona, worker) — an independent reviewer that never
  wrote or fixed the code. It signs off only when CI is green, no thread is
  unresolved, and the change follows this file and does what the PR says. It
  posts exactly one verdict per review round: `[Arbiter] ✅ Signed off` with a
  short rationale, or `[Arbiter] ❌ Changes requested` with a numbered list for
  the PR Reviewer to address before the next round. It never pushes code.
- **Tech Coordinator** — Leo's GrokBot. It may leave review feedback and merge.

### Identity rule

Every agent, the Tech Coordinator included, posts through Leo's own GitHub
account. GitHub will not let an author approve their own PR, so its Approve
review is unavailable, and comment authors are indistinguishable. Therefore:

- Every agent-written comment or reply starts with its role tag in brackets:
  `[Implementer]`, `[PR Reviewer]`, `[Arbiter]`, `[Tech Coordinator]`.
- A comment with no tag is from Leo and takes priority.
- The Arbiter's `✅ Signed off` comment is the approval of record. Post it with
  `gh pr comment` or `gh pr review --comment`; never use `--approve`.

### Merging

Agents never merge. Leo or the Tech Coordinator merges once the Arbiter has
signed off on the latest commit. A sign-off covers only the commit it reviewed,
so any commit pushed after it needs a fresh Arbiter verdict.
