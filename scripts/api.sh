#!/usr/bin/env sh
# Reachability checks for the *hosted* Energlens API.
#
#   scripts/api.sh preflight [url]   assert an Energlens API answers at <url>/health
#   scripts/api.sh smoke [url]       preflight + the deployed commit + OpenAPI contract
#   scripts/api.sh validate [url]    the offline half only: shape and format
#
# <url> defaults to $API_URL. With neither, and outside Actions, it falls back to
# `gh variable get API_URL` — the exact value deploy-frontend.yml bakes into the
# bundle. Never in Actions: there the workflow passes the value, and reading a
# second source would let an unset repository variable pass a check the build
# then fails on.
#
# Why this exists: *.onrender.com is a wildcard, so a typo'd, guessed or
# decommissioned service returns a plain HTTP 404 instead of failing DNS. Nothing
# downstream can catch that — API_URL is inlined at *build* time — so every check
# stays green and the SPA reports "Login failed — is the API running?" (issue #11).
#
# smoke exists because /health alone is not enough: a live process can still be
# serving yesterday's commit (issue #48). The OpenAPI contract could not answer
# that either — it holds on the previous revision too, so a smoke run ten
# seconds after a merge went green against the old deploy (issues #91, #97). So
# smoke waits until /health names a commit that contains the one under test.
#
# Every failure path prints the command that fixes it.
set -eu

# Retry budget. Two failures have to be survived and they want opposite things:
#
#   * Cold start. The free tier sleeps after 15 min and the wake HANGS the
#     request — measured >40s with zero bytes received, then success seconds
#     later, because giving up client-side does not cancel the wake. This wants
#     total budget across attempts, not a long single attempt.
#   * Edge flap. Right after a service is created, Render's edge alternated
#     between the app and a no-server 404 for ~12 min at roughly 50% (issue #13).
#     Those fail in ~0.1s, so a long --max-time buys nothing at all; only fresh
#     connections do.
#
# 10 attempts x 30s, 5s apart = up to ~345s over 10 independent connections:
# >5x the documented 30-60s cold start, enough to ride out a Render restart, and
# at a 50% flap rate the odds of ten consecutive false failures are 1 in 1024.
ATTEMPTS="${API_PREFLIGHT_ATTEMPTS:-10}"
INTERVAL="${API_PREFLIGHT_INTERVAL:-5}"
TIMEOUT="${API_PREFLIGHT_TIMEOUT:-30}"
# Separate and short: TLS terminates at Render's edge, which is up even while the
# instance wakes. A slow *connect* therefore means a dead host, not a cold one —
# retry rather than burn the whole per-attempt budget on it.
CONNECT_TIMEOUT="${API_PREFLIGHT_CONNECT_TIMEOUT:-10}"

say() { printf '%s\n' "$*" >&2; }
die() { printf '%s\n' "$*" >&2; exit 1; }
note() { printf '%s\n' "$*"; }

have() { command -v "$1" >/dev/null 2>&1; }

# Annotations only under Actions: locally they are noise on top of a message the
# human already has in front of them.
annotate() { [ -z "${GITHUB_ACTIONS:-}" ] || printf '::%s::%s\n' "$1" "$2"; }

# Collapsed to one line and truncated: a 200 KB HTML error page is not a
# diagnostic, and an annotation is line-oriented.
excerpt() { printf '%.200s' "$(printf '%s' "$1" | tr -d '\r' | tr '\n' ' ')"; }

# Tolerates pretty-printed JSON, and turns Render's "Not Found\n" into a token
# that can be compared exactly rather than grepped for.
squeeze() { printf '%s' "$1" | tr -d '[:space:]'; }

# Exact, not grepped: the body is what says "this is *our* API". A revision from
# before issue #91 answers {"status":"ok"}; a current one adds fields after the
# status. Both are an Energlens API, and preflight must accept either — it gates
# frontend deploys, and must not fail them while a backend deploy is in flight.
health_ok() {
  case "$(squeeze "$1")" in
    '{"status":"ok"}' | '{"status":"ok",'*'}') return 0 ;;
  esac
  return 1
}

# The commit a /health body names, or "unknown" when it names none — which is
# also what a revision that predates the field (issue #91) amounts to. Hex only:
# the value goes to git as a revision, and "main" or "HEAD" would resolve there
# and pass the ancestry check without naming any deploy at all.
served_commit() {
  sc="$(squeeze "$1" | sed -n 's/.*"commit":"\([0-9a-f]\{7,40\}\)".*/\1/p')"
  printf '%s' "${sc:-unknown}"
}

git_repo() { git -C "$(dirname "$0")" "$@"; }

# The commit that must be live for smoke to pass. Not simply HEAD: render.yaml
# sets rootDir: backend, and Render only auto-deploys a push that changes files
# under the root directory (https://render.com/docs/monorepo-support). A commit
# that touches only scripts/ or frontend/ is never served, so waiting for it
# would time out against a perfectly current API. The newest commit that changed
# backend/ is the one a finished deploy must contain.
#
# In Actions that is measured from the commit under test; locally from
# origin/main as of your last fetch, which is what the deploy follows.
# API_EXPECT_COMMIT overrides both.
expected_commit() {
  if [ -n "${API_EXPECT_COMMIT:-}" ]; then
    expected="$API_EXPECT_COMMIT"
    expected_why="API_EXPECT_COMMIT"
    return 0
  fi

  have git || die "error: no git on PATH, so smoke cannot tell which commit should be live.
     Fix: install git, or set API_EXPECT_COMMIT=<sha>"

  if [ -n "${GITHUB_ACTIONS:-}" ]; then
    ref="${GITHUB_SHA:-HEAD}"
  else
    ref=origin/main
  fi

  # :/ anchors the pathspec at the repository root, whatever the caller's cwd.
  expected="$(git_repo log -1 --format=%H "$ref" -- ':/backend' 2>/dev/null || true)"
  [ -n "$expected" ] || die "error: found no commit under backend/ reachable from $ref.
     A shallow clone is the usual cause: actions/checkout needs fetch-depth: 0.
     Fix: git fetch origin   (or set API_EXPECT_COMMIT=<sha>)"
  expected_why="newest commit under backend/ in $ref"
}

# Live means the served commit *contains* the expected one, not equals it: a
# later merge may already have deployed by the time this run polls, and that is
# a current API, not a stale one. A served commit this clone has never seen is
# fetched once by SHA; if it is still unknown — "unknown" itself, a short SHA
# from a rewritten history — it cannot be proved live, so it is not.
commit_is_live() {
  [ "$1" != unknown ] || return 1
  git_repo cat-file -e "$1^{commit}" 2>/dev/null ||
    git_repo fetch --quiet origin "$1" 2>/dev/null ||
    true
  git_repo merge-base --is-ancestor "$2" "$1" 2>/dev/null
}

fix_url() {
  say ""
  say "Fix: read the hostname off the Render service page — Render appends a suffix"
  say "     when the name is taken — then:"
  say "       gh variable set API_URL --body https://<service>.onrender.com"
  say "       make api-preflight            # confirm it answers, before deploying"
  say "       gh workflow run \"Deploy frontend to GitHub Pages\""
  say "     The last line is not optional: API_URL is inlined at build time and the"
  say "     workflow's paths filter is frontend/**, so setting the variable deploys"
  say "     nothing on its own."
}

# Opposite failure mode from fix_url: the hostname is right and /health is green,
# but the revision is stale. Point at Render, not at API_URL (issue #48).
fix_stale() {
  say ""
  say "Fix: the API is up but it is serving an older revision than main."
  say "     In the Render dashboard: energlens-api → Manual Deploy → Deploy latest commit."
  say "     Confirm Auto Deploy is On Commit (render.yaml sets autoDeployTrigger: commit)."
  say "     If the Blueprint did not pick that up, Manual Sync the Blueprint once."
  say "     Then: make api-smoke"
}

reject() {
  say "Repository variable API_URL $1 (got: '${2:-<empty>}')."
  fix_url
  annotate error "Repository variable API_URL $1 (got: '${2:-<empty>}')."
  exit 1
}

# The failure-mode table this check exists to disambiguate. "The deploy failed
# and here is a 404" is precisely the ambiguity issue #11 was filed about, so
# each branch names what is actually wrong.
diagnose() {
  html=no
  case "$(squeeze "$body")" in '<'*) html=yes ;; esac

  case "$code" in
    000)
      say "No HTTP response at all — curl exited $rc: $(excerpt "$body")"
      case "$rc" in
        6) say "The hostname does not resolve. That is a typo, not a sleeping service." ;;
        7) say "Connection refused: the name resolves but nothing is listening." ;;
        28)
          say "Every attempt timed out. A free-tier cold start takes 30-60s and this"
          say "waited up to $((ATTEMPTS * TIMEOUT))s across $ATTEMPTS attempts, so the service is not"
          say "merely asleep — check the Render dashboard for a failed or stuck deploy."
          ;;
        35 | 60) say "TLS failed. Check the certificate presented by this host." ;;
      esac
      ;;
    2*)
      if [ "$html" = yes ]; then
        say "HTTP $code with an HTML body — a website answers here, not the Energlens"
        say "API. Pointing API_URL at the Pages origin is the usual version of this."
      else
        say "HTTP $code, but the body is not {\"status\":\"ok\"} — something answers here"
        say "and it is not an Energlens API. Body: $(excerpt "$body")"
      fi
      ;;
    3*)
      say "HTTP $code — this URL redirects, and API_URL has to be the final origin."
      say "Browsers do not follow redirects on a CORS preflight, so every write would"
      say "fail in the browser even though 'curl -L' would look fine here."
      ;;
    404)
      if [ "$(squeeze "$body")" = "NotFound" ]; then
        say "HTTP 404 with a plain-text 'Not Found' body: no service claims this"
        say "hostname. *.onrender.com is a wildcard, so a guessed, typo'd or"
        say "decommissioned host answers exactly like this instead of failing DNS."
        say "Confirm with:  curl -sSi $probe | head -5"
        say "The tell is the response header 'x-render-routing: no-server'."
      elif [ "$html" = yes ]; then
        say "HTTP 404 and the body is HTML — API_URL points at a website, not an API."
      else
        say "HTTP 404 with a JSON body — an Energlens app is up, but /health is not"
        say "routed here. API_URL probably carries a path suffix, or the deployed"
        say "revision predates /health. Body: $(excerpt "$body")"
      fi
      ;;
    405)
      say "HTTP 405 — a server here serves /health but refuses GET. Ours accepts GET"
      say "and only GET (FastAPI does not auto-register HEAD for @app.get), so this"
      say "is something else, or something is rewriting the method in front of it."
      ;;
    5*)
      say "HTTP $code — a server is up and failing. Check the Render logs: start.sh"
      say "aborts the boot under set -e when DATABASE_URL is wrong, and the free tier"
      say "has one instance, so a redeploy briefly answers like this."
      ;;
    *)
      say "HTTP $code. Body: $(excerpt "$body")"
      ;;
  esac
}

# Readiness, reported and never enforced. A red /health/db is a Neon problem, and
# failing a frontend deploy for it is the wrong blast radius (docs/adr/0014-*.md)
# — but saying nothing ships a green deploy onto a dead database. One attempt,
# because this is advisory.
check_db() {
  [ "${API_PREFLIGHT_CHECK_DB:-1}" = 1 ] || return 0
  db_out="$(curl -sS --connect-timeout "$CONNECT_TIMEOUT" --max-time "$TIMEOUT" \
    -w '|HTTP:%{http_code}' "$url/health/db" 2>&1)" || true
  db_code="${db_out##*|HTTP:}"
  [ "$db_code" != "200" ] || return 0
  say "warning: $url/health/db answered HTTP $db_code — the API is up but its database"
  say "         is not. The deploy continues on purpose (docs/adr/0014-*.md); check"
  say "         Neon and the Render logs. Body: $(excerpt "${db_out%|HTTP:*}")"
  annotate warning "$url/health/db answered HTTP $db_code — API up, database unreachable."
}

# The offline half: everything that can be decided without a network round trip.
# Split out so the deploy's escape hatch can skip the *probe* without also
# skipping this — a backend outage is a reason not to trust the network, not a
# reason to ship a bundle pointed at an empty or malformed URL. Sets `url` to the
# resolved, normalised value for the caller.
resolve_url() {
  url="${1:-${API_URL:-}}"

  if [ -z "$url" ] && [ -z "${GITHUB_ACTIONS:-}" ] && have gh; then
    url="$(gh variable get API_URL 2>/dev/null || true)"
    [ -z "$url" ] || say "note: no URL given — checking repository variable API_URL ($url)"
  fi

  # A trailing newline or space is the classic `gh variable set --body "$(...)"`
  # paste artifact. curl then rejects the URL with an error naming neither the
  # variable nor the whitespace. Named rather than silently trimmed: a silent
  # trim leaves the repository variable wrong forever.
  [ "$url" = "$(squeeze "$url")" ] || reject "must not contain whitespace" "$url"

  # client.ts does `new URL(API_URL + path)`, so a query string or fragment lands
  # in the middle of every request path. A path *prefix* is fine and supported.
  case "$url" in
    *\?* | *\#*) reject "must not carry a query string or fragment" "$url" ;;
  esac

  # Shape, not just emptiness: Render's dashboard shows the bare host, and a
  # scheme-less value sails through `test -n` and then throws "Invalid URL" from
  # new URL() on every request. Moved here from deploy-frontend.yml's Build step
  # so one command validates the variable, locally and in CI alike.
  case "$url" in
    https://?*) ;;
    http://localhost | http://localhost[:/]* | http://127.0.0.1 | http://127.0.0.1[:/]*)
      # Local only, so `make dev-api` + `make api-preflight API_URL=http://localhost:8000`
      # exercises the *success* path with no production dependency. Never in CI:
      # a repository variable pointing at localhost is exactly the bundle this
      # check exists to stop.
      [ -z "${GITHUB_ACTIONS:-}" ] || reject "must be an absolute https:// URL" "$url"
      say "note: plain-http loopback accepted locally; the deploy requires https://"
      ;;
    *) reject "must be an absolute https:// URL" "$url" ;;
  esac

  # Strip every trailing slash, exactly as client.ts does (/\/+$/), so this check
  # and the running SPA build the same URL. Stripping only one would probe
  # //health for a value ending in "//" and fail against a healthy API.
  url="$(printf '%s' "$url" | sed 's|/*$||')"
}

cmd_validate() {
  resolve_url "$@"
  note "  API_URL shape ok — $url (not probed)"
}

cmd_preflight() {
  resolve_url "$@"

  have curl || die "error: no curl on PATH.
     Fix: brew install curl   (every GitHub Actions runner has it preinstalled)"

  probe="$url/health"

  # /health, never /health/db. /health/db is the readiness half and *should* go
  # red during a Neon outage (docs/adr/0014-*.md); gating on it would block a
  # frontend-only deploy on a backend-only fault.
  n=1
  while :; do
    rc=0
    out="$(curl -sS --connect-timeout "$CONNECT_TIMEOUT" --max-time "$TIMEOUT" \
      -w '|HTTP:%{http_code}' "$probe" 2>&1)" || rc=$?
    # --write-out is emitted last even on a failed transfer and even with curl's
    # own error merged in from stderr, so ## takes the code and % takes the body.
    # No -f: it exits nonzero but discards the body, and the body is the whole
    # diagnosis. No -L: see the 3xx branch.
    code="${out##*|HTTP:}"
    body="${out%|HTTP:*}"

    # Status AND body. `curl -sS` without -f exits 0 on a 404, so the exit status
    # is not a signal; 2xx alone would accept any server that happens to answer.
    # The body is what says "this is *our* API".
    if [ "$code" = "200" ] && health_ok "$body"; then
      note "  API_URL ok — $probe served {\"status\":\"ok\"} (attempt $n/$ATTEMPTS)"
      check_db
      return 0
    fi

    [ "$n" -lt "$ATTEMPTS" ] || break
    say "  attempt $n/$ATTEMPTS: HTTP $code — retrying in ${INTERVAL}s"
    n=$((n + 1))
    sleep "$INTERVAL"
  done

  summary="API_URL ($url) did not serve {\"status\":\"ok\"} at /health after $ATTEMPTS attempts"
  say ""
  say "$summary."
  say ""
  diagnose
  fix_url
  annotate error "$summary. Last response: HTTP $code."
  exit 1
}

# OpenAPI contract for "is this revision current enough". /health proves the
# process; this proves the surface. Exit 0 ok, 2 wrong title, 3 missing delete.
check_openapi_contract() {
  have python3 || die "error: no python3 on PATH.
     Fix: install Python 3 (GitHub Actions runners have it; locally: brew install python)"

  oa_rc=0
  oa_out="$(curl -sS --connect-timeout "$CONNECT_TIMEOUT" --max-time "$TIMEOUT" \
    -w '|HTTP:%{http_code}' "$url/openapi.json" 2>&1)" || oa_rc=$?
  oa_code="${oa_out##*|HTTP:}"
  oa_body="${oa_out%|HTTP:*}"

  if [ "$oa_code" != "200" ]; then
    say "  openapi: HTTP $oa_code (curl exit $oa_rc) — $(excerpt "$oa_body")"
    return 1
  fi

  # python exits: 0 ok, 2 wrong/missing title, 3 missing DELETE /users/me, 1 parse
  py_rc=0
  printf '%s' "$oa_body" | python3 -c '
import json, sys
try:
    doc = json.load(sys.stdin)
except json.JSONDecodeError as e:
    print(f"openapi: not JSON ({e})", file=sys.stderr)
    sys.exit(1)
title = (doc.get("info") or {}).get("title")
if title != "Energlens API":
    print(f"openapi: title is {title!r}, expected \"Energlens API\"", file=sys.stderr)
    sys.exit(2)
methods = (doc.get("paths") or {}).get("/users/me") or {}
if "delete" not in methods:
    keys = sorted(methods)
    print(f"openapi: /users/me has {keys}, missing delete", file=sys.stderr)
    sys.exit(3)
' || py_rc=$?

  case "$py_rc" in
    0)
      note "  openapi ok — title Energlens API, DELETE /users/me present"
      return 0
      ;;
    2 | 3)
      return "$py_rc"
      ;;
    *)
      return 1
      ;;
  esac
}

# Stronger than preflight: waits until /health is green, names a commit that
# contains the one under test, *and* OpenAPI shows the public contract that would
# have caught issue #48. Used after backend merges (Render deploys out-of-band)
# and on a daily cron. Raise ATTEMPTS/INTERVAL via the env knobs above when
# waiting on a free-tier build: the deploy is *expected* to lag the merge, so a
# stale commit is retried, and only fails once the whole budget is spent.
cmd_smoke() {
  resolve_url "$@"

  have curl || die "error: no curl on PATH.
     Fix: brew install curl   (every GitHub Actions runner has it preinstalled)"

  expected_commit
  note "  waiting for commit $expected ($expected_why)"

  probe="$url/health"
  n=1
  last_health=down
  last_commit=pending
  last_openapi=pending
  served=unknown
  while :; do
    rc=0
    out="$(curl -sS --connect-timeout "$CONNECT_TIMEOUT" --max-time "$TIMEOUT" \
      -w '|HTTP:%{http_code}' "$probe" 2>&1)" || rc=$?
    code="${out##*|HTTP:}"
    body="${out%|HTTP:*}"

    if [ "$code" = "200" ] && health_ok "$body"; then
      last_health=ok
      served="$(served_commit "$body")"
      if commit_is_live "$served" "$expected"; then
        last_commit=ok
        note "  API_URL ok — $probe serves commit $served, which contains $expected (attempt $n/$ATTEMPTS)"
        check_db
        if check_openapi_contract; then
          last_openapi=ok
          return 0
        fi
        last_openapi=stale
      else
        last_commit=stale
        last_openapi=pending
      fi
    else
      last_health=down
      last_commit=pending
      last_openapi=pending
    fi

    [ "$n" -lt "$ATTEMPTS" ] || break
    say "  attempt $n/$ATTEMPTS: health=$last_health commit=$last_commit${served:+ ($served)} openapi=$last_openapi — retrying in ${INTERVAL}s"
    n=$((n + 1))
    sleep "$INTERVAL"
  done

  say ""
  if [ "$last_health" = ok ] && [ "$last_commit" = stale ]; then
    summary="Deploy is stale: API_URL ($url) serves commit $served, not $expected or a descendant, after $ATTEMPTS attempts"
    say "$summary."
    if [ "$served" = unknown ]; then
      say "/health names no commit, so the revision answering predates issue #91 —"
      say "older than the change that added the field, and so older than main."
    else
      say "The process is up and answering, but from an older commit than the one"
      say "under test: the deploy has not happened, or has not finished."
    fi
    fix_stale
    annotate error "$summary."
    exit 1
  fi

  if [ "$last_health" = ok ] && [ "$last_openapi" = stale ]; then
    summary="API_URL ($url) serves commit $served but its OpenAPI contract does not hold after $ATTEMPTS attempts"
    say "$summary."
    say "The deploy is current, so this is not issue #48: the app on main no longer"
    say "matches what check_openapi_contract in scripts/api.sh asserts. Fix whichever"
    say "of the two is wrong, then: make api-smoke"
    annotate error "$summary."
    exit 1
  fi

  summary="API_URL ($url) did not serve {\"status\":\"ok\"} at /health after $ATTEMPTS attempts"
  say "$summary."
  say ""
  diagnose
  fix_url
  annotate error "$summary. Last response: HTTP $code."
  exit 1
}

case "${1:-preflight}" in
  preflight)
    [ "$#" -eq 0 ] || shift
    cmd_preflight "${1:-}"
    ;;
  smoke)
    shift
    cmd_smoke "${1:-}"
    ;;
  validate)
    shift
    cmd_validate "${1:-}"
    ;;
  -h | --help | help)
    say "usage: $0 preflight [url]   # shape + reachability"
    say "       $0 smoke     [url]   # preflight + deployed commit + OpenAPI contract"
    say "       $0 validate  [url]   # shape only, no network"
    ;;
  *) die "usage: $0 [preflight|smoke|validate] [url]" ;;
esac
