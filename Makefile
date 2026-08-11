# Energlens — the single command surface.
#
# Every operation an agent or a contributor needs is a target here, so nobody
# has to know whether a given job is uv, npm, alembic or a shell script, and no
# harness needs an allowlist beyond "allow make".
#
# Written for GNU Make 3.81 (Apple's stock /usr/bin/make, 2006): no .ONESHELL,
# no `!=` assignment, no $(file ...). Each recipe line runs in its own shell, so
# recipes stay short and anything with branching lives in scripts/.

# Absolute, so targets behave the same from a subdirectory or via `make -C`.
ROOT := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))

DB      := $(ROOT)/scripts/db.sh
UV      := uv
BACKEND := $(UV) run --directory $(ROOT)/backend
INGEST  := $(UV) run --directory $(ROOT)/ingest
WEB     := cd $(ROOT)/frontend &&

# `make test-backend PYTEST_ARGS="-k currency"`. Without this, running a single
# test means bypassing make — and losing the preflight that explains why the
# database is unreachable.
PYTEST_ARGS ?=

# Marker file, not the directory: npm mutates node_modules/ after `npm ci`, so
# the directory's mtime is newer than the lockfile and the rule never fires.
NODE_STAMP := $(ROOT)/frontend/node_modules/.package-lock.json

# Database work must not interleave under `make -j`.
.NOTPARALLEL:
.DEFAULT_GOAL := help

# Only names with rules below. A phony target with no recipe exits 0 while
# doing nothing, which on the repo's authoritative command surface reads as
# "it passed"; a missing target at least fails loudly. fmt/lint/lint-py/lint-web
# arrive with the linters that back them.
.PHONY: help setup env db-up db-down db-ensure db-reset db-shell db-preflight \
        migrate migration migrate-check lock-check seed dev-api dev-web \
        typecheck build-web \
        test test-backend test-ingest test-frontend \
        check ci-backend ci-frontend clean

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

## -- setup ------------------------------------------------------------------

setup: env $(NODE_STAMP) ## Install every dependency and create .env if missing
	$(UV) sync --directory $(ROOT)/backend
	$(UV) sync --directory $(ROOT)/ingest

# Both lines must succeed whatever state .env is in: this is the first thing a
# new clone runs, and `test -s` on a zero-byte .env would abort `make setup`.
env: ## Create .env from .env.example if it does not exist yet
	@test -f $(ROOT)/.env || { cp $(ROOT)/.env.example $(ROOT)/.env; \
	  echo "created .env from .env.example"; }
	@test -s $(ROOT)/.env || echo "warning: .env is empty — copy .env.example into it"

$(NODE_STAMP): $(ROOT)/frontend/package-lock.json
	$(WEB) npm ci

## -- database ---------------------------------------------------------------

db-up: ## Start Postgres (project-local cluster, or docker compose)
	@$(DB) up

db-down: ## Stop Postgres
	@$(DB) down

db-ensure: ## Create any missing databases (idempotent; used by CI too)
	@$(DB) ensure

db-reset: ## DROP and recreate both databases, then migrate and seed
	@$(DB) reset
	@$(MAKE) migrate seed

db-shell: ## Open psql on the app database
	@$(DB) shell dev

db-preflight: ## Explain why the test database is unusable, if it is
	@$(DB) preflight test

## -- migrations -------------------------------------------------------------

migrate: ## Apply migrations to the app database
	@$(DB) preflight dev
	$(BACKEND) alembic upgrade head

# Mirrors the "Migrations apply and match the models" step in backend-ci.yml.
# Runs against a throwaway database built by Alembic alone: the test database's
# schema comes from Base.metadata.create_all, so checking that one would compare
# the models against themselves and never see the drift.
migrate-check: ## Assert migrations apply cleanly and match the models
	@$(DB) scratch
	DATABASE_URL="$$($(DB) url scratch)" $(BACKEND) alembic upgrade head
	DATABASE_URL="$$($(DB) url scratch)" $(BACKEND) alembic check

migration: ## New migration: make migration m="add reference to bill"
	@test -n "$(m)" || { echo 'usage: make migration m="short description"' >&2; exit 1; }
	@$(DB) preflight dev
	$(BACKEND) alembic revision --autogenerate -m "$(m)"
	@echo "Review the generated file before committing — autogenerate cannot see"
	@echo "renames (it emits drop+add, which loses data). See docs/migrations.md."

seed: ## Load demo data (demo@example.com / demo1234)
	@$(DB) preflight dev
	$(BACKEND) python -m app.seed

## -- run --------------------------------------------------------------------

dev-api: ## Run the API at http://localhost:8000 (docs at /docs)
	@$(DB) preflight dev
	$(BACKEND) uvicorn app.main:app --reload

dev-web: $(NODE_STAMP) ## Run the SPA at http://localhost:5173
	$(WEB) npm run dev

## -- quality ----------------------------------------------------------------

typecheck: $(NODE_STAMP) ## Typecheck the frontend
	$(WEB) npm run typecheck

build-web: $(NODE_STAMP) ## Production build of the frontend
	$(WEB) npm run build

test: test-backend test-ingest test-frontend ## Run every test suite

test-backend: ## Backend pytest. PYTEST_ARGS="-k currency" to narrow.
	@$(DB) preflight test
	$(BACKEND) pytest -q $(PYTEST_ARGS)

test-ingest: ## Ingest pytest (never calls a paid API)
	$(INGEST) pytest -q $(PYTEST_ARGS)

test-frontend: typecheck ## The frontend has no test runner; typecheck is the gate

## -- the gate ---------------------------------------------------------------

# `make check` is the union of the merge-gating CI jobs, so the two cannot
# disagree. deploy-frontend.yml is deliberately not included: it is a deploy,
# not a gate, and depends on production-only repository variables.
check: ci-backend ci-frontend ## Run everything CI runs. The gate.

# CI installs with `uv sync --locked`, which refuses to re-lock; local `uv run`
# re-locks silently, so without this a pyproject edit passes `make check` and
# then fails the build. Checked rather than enforced, so editing pyproject.toml
# locally still works — the failure names `uv lock` as the fix.
lock-check: ## Assert both uv.lock files still match their pyproject.toml
	$(UV) lock --check --directory $(ROOT)/backend
	$(UV) lock --check --directory $(ROOT)/ingest

# Same order as backend-ci.yml: the migration gate runs before the suites.
ci-backend: lock-check migrate-check test-backend test-ingest

# Depends on test-frontend rather than relying on build-web to run tsc first, so
# that adding a real frontend test runner to test-frontend lands in `make check`
# automatically instead of silently escaping the gate.
ci-frontend: test-frontend build-web

clean: ## Remove build output and caches
	rm -rf $(ROOT)/frontend/dist $(ROOT)/frontend/node_modules/.tmp
	find $(ROOT) -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
