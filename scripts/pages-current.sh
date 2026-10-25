#!/usr/bin/env sh
# Assert that the deployed Pages site is not behind main.
#
#   scripts/pages-current.sh               check this repo (GITHUB_REPOSITORY in CI)
#
#   GRACE_MINUTES  how long an undeployed commit may wait before it counts as
#                  stale (default 30 — a deploy takes about three)
#
# A push to main once produced no workflow run at all (issue #95). The deploy's
# own `alert` job lives inside deploy-frontend.yml, and a run that is never
# created cannot fail, so it cannot alert: the merge looks normal and the site
# silently keeps serving the previous commit. So rather than watching for
# something to fail, this compares two facts that exist whatever went wrong —
# the commits on main, and the sha of the live github-pages deployment.
#
# Not main's HEAD against that sha, though: deploy-frontend.yml has a `paths`
# filter, so a backend-only merge rightly deploys nothing and HEAD runs ahead of
# the site all the time. What must be deployed is every commit on main that
# touches one of those paths. DEPLOY_PATHS below is a copy of that filter;
# backend/tests/test_pages_current.py fails if the two drift.
#
# Every failure path prints the command that fixes it (issue #2, principle 5).
set -eu

say() { printf '%s\n' "$*" >&2; }
die() { printf '%s\n' "$*" >&2; exit 1; }

REDEPLOY='Fix: gh workflow run "Deploy frontend to GitHub Pages" --ref main'

BRANCH=main
DEPLOY_PATHS="frontend .github/workflows/deploy-frontend.yml"
GRACE_MINUTES="${GRACE_MINUTES:-30}"

case "$GRACE_MINUTES" in
  ''|*[!0-9]*) die "error: GRACE_MINUTES must be a whole number of minutes, got '$GRACE_MINUTES'." ;;
esac

command -v gh >/dev/null 2>&1 || die "error: no gh on PATH.
     Fix: brew install gh   (in Actions, pass GH_TOKEN)"

# gh expands {owner}/{repo} from the current checkout, so this also runs locally.
if [ -n "${GITHUB_REPOSITORY:-}" ]; then
  REPO="$GITHUB_REPOSITORY"
else
  REPO='{owner}/{repo}'
fi

api() {
  gh api "repos/$REPO/$1" --jq "$2" 2>/dev/null || die "error: GET repos/$REPO/$1 failed.
     Locally  : gh is not authenticated.   Fix: gh auth login
     In CI    : the job is missing GH_TOKEN, or 'permissions: deployments: read'."
}

# --- the live deployment -----------------------------------------------------

# The newest *successful* one, not the newest one: a deployment record exists
# from the moment the deploy job starts, so a run in flight or one that failed
# would otherwise count as live. When a deployment succeeds, GitHub marks the
# ones before it `inactive`, so the first `success` is the one being served.
# Assigned before the loop, not inside `for … in $(…)`: set -e does not see a
# failed command substitution in a word list, and would loop over nothing.
# `per_page=1` reads the latest status because GitHub lists a deployment's
# statuses newest first; that ordering is documented, but this relies on it.
deployments="$(api "deployments?environment=github-pages&per_page=30" '.[] | "\(.id):\(.sha)"')"
DEPLOYED=""
for line in $deployments; do
  state="$(api "deployments/${line%%:*}/statuses?per_page=1" '.[0].state // ""')"
  if [ "$state" = success ]; then
    DEPLOYED="${line#*:}"
    break
  fi
done

[ -n "$DEPLOYED" ] || die "error: no successful github-pages deployment among the 30 most recent.
     The site may not be serving at all.
     $REDEPLOY"

say "pages-current: live deployment is $DEPLOYED"

# --- what main has that the deployment does not ------------------------------

# One request: status, ahead_by, then the sha and committer time (epoch
# seconds) of each commit main has that the deployment does not, oldest first.
# For a squash merge the committer time is the moment it landed on main — and
# main is squash-only, so that is the grace clock. A merge commit would also
# list the branch's own commits, with committer times that can be days old, and
# could fail inside the grace window; switch to first-parent landing times if
# merge commits are ever allowed.
compare="$(api "compare/$DEPLOYED...$BRANCH" '.status, .ahead_by, (.commits[] | "\(.sha):\(.commit.committer.date | fromdateiso8601)")')"
status="$(printf '%s\n' "$compare" | sed -n 1p)"
ahead_by="$(printf '%s\n' "$compare" | sed -n 2p)"
undeployed="$(printf '%s\n' "$compare" | sed '1,2d')"

# `diverged` means the live sha is not on main at all — a workflow_dispatch from
# another branch — and `behind` that main was reset past it. Either way the
# site is not serving main.
case "$status" in
  identical|ahead) ;;
  *) die "error: the live deployment $DEPLOYED is not an ancestor of $BRANCH (compare: $status).
     The site is serving a commit that main does not contain.
     $REDEPLOY" ;;
esac

if [ "$ahead_by" -eq 0 ]; then
  say "pages-current: ok — the live deployment is $BRANCH's HEAD"
  exit 0
fi

# The compare endpoint lists at most 250 commits. That far behind, the answer
# does not depend on which of them touched the deploy paths.
listed="$(printf '%s\n' "$undeployed" | grep -c . || true)"
[ "$listed" -ge "$ahead_by" ] || die "error: the live deployment is $ahead_by commits behind $BRANCH — more than can be listed.
     $REDEPLOY"

# Commits on main that touch a deploy path. Only the ones newer than the live
# deployment matter, and those are among the $ahead_by newest.
# The API caps a page at 100. Beyond that the listing can miss older relevant
# commits, which still fails correctly — something newer is undeployed too —
# but the count and the oldest are only a lower bound, and the message says so.
per_page=$((ahead_by < 100 ? ahead_by : 100))
at_least=""
[ "$ahead_by" -le 100 ] || at_least="at least "
relevant=""
for path in $DEPLOY_PATHS; do
  touched="$(api "commits?sha=$BRANCH&path=$path&per_page=$per_page" '.[].sha')"
  relevant="$relevant
$touched"
done

# --- decide ------------------------------------------------------------------

now="$(date +%s)"
grace=$((GRACE_MINUTES * 60))
oldest=""
oldest_at=""
count=0
for sha_at in $undeployed; do
  sha="${sha_at%%:*}"
  printf '%s\n' "$relevant" | grep -qx "$sha" || continue
  count=$((count + 1))
  if [ -z "$oldest" ]; then
    oldest="$sha"
    oldest_at="${sha_at#*:}"
  fi
done

if [ "$count" -eq 0 ]; then
  say "pages-current: ok — $BRANCH is $ahead_by commit(s) ahead, none of them touching: $DEPLOY_PATHS"
  exit 0
fi

age=$((now - oldest_at))
if [ "$age" -lt "$grace" ]; then
  say "pages-current: ok for now — $count undeployed commit(s), the oldest ($oldest) landed $((age / 60)) min ago, within the ${GRACE_MINUTES} min grace."
  exit 0
fi

die "error: the live site is behind $BRANCH.
     $at_least$count commit(s) touching the deploy paths are not deployed; the oldest
     listed, $oldest, landed $((age / 60)) min ago.
     Live deployment : $DEPLOYED
     Either no deploy run was created for the push (issue #95), or every run
     since has failed — check the Actions tab for 'Deploy frontend to GitHub Pages'.
     $REDEPLOY"
