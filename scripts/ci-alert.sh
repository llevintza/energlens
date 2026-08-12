#!/usr/bin/env sh
# Turn a workflow's job results into a tracking issue, and close it on recovery.
#
#   scripts/ci-alert.sh <topic> "<results>" <run-url>
#
#   topic    short slug; picks the label (ci:<topic>) and the issue title
#   results  the job results, space-separated — ${{ join(needs.*.result, ' ') }}
#   run-url  link back to the run that produced them
#
# The Pages deploy runs on push to main, after the PR is gone, so it can never
# be a required status check — a red deploy blocks nothing and, before this,
# announced nothing. It went unnoticed for five hours once (issue #10). An
# issue is the one signal that reaches a human without anyone thinking to look.
#
# Recovery closes it again. An alert that only ever opens becomes a stale issue
# nobody trusts, which is the same as no alert.
set -eu

say() { printf '%s\n' "$*" >&2; }
die() { printf '%s\n' "$*" >&2; exit 1; }

[ $# -eq 3 ] || die "usage: scripts/ci-alert.sh <topic> \"<results>\" <run-url>"

TOPIC="$1"
RESULTS="$2"
RUN_URL="$3"

command -v gh >/dev/null 2>&1 || die "error: no gh on PATH.
     Fix: brew install gh   (in Actions, use actions/checkout and GH_TOKEN)"

LABEL="ci:$TOPIC"
TITLE="CI alert: $TOPIC is failing on main"

# --- decide -----------------------------------------------------------------

# Any `failure` opens; only an all-`success` run closes; everything else is
# silence. deploy-frontend.yml sets cancel-in-progress on the `pages`
# concurrency group, so a superseded run reports `cancelled` — filing on that
# would alert on every quick second push. `skipped` is equally uninformative:
# it means an upstream job never ran, which the failure itself already covers.
#
# Checked in that order, not first-match-wins: `cancelled failure` is a real
# failure that happens to have a cancelled sibling, and must still be reported.
case " $RESULTS " in
  *" failure "*)
    verdict=failing
    ;;
  *)
    verdict=recovered
    seen=0
    for result in $RESULTS; do
      seen=$((seen + 1))
      [ "$result" = success ] || verdict=inconclusive
    done
    # No results at all means a misconfigured caller, not that all is well.
    [ "$seen" -gt 0 ] || verdict=inconclusive
    ;;
esac

if [ "$verdict" = inconclusive ]; then
  say "ci-alert: results '$RESULTS' are neither a clean pass nor a failure — nothing to say."
  exit 0
fi

# --- find the open issue for this topic -------------------------------------

# Matched by label, not by title: the title can be edited by a human without
# breaking the dedup, and a label cannot be typo'd into a second issue.
#
# Issue listings are served from an index that lags a second or two behind
# writes, in both directions — measured on this repo. Both directions bite:
#
#   stale hit   a just-closed issue still lists as open, so the green path
#               comments on and re-closes it, and the red path attaches a new
#               failure to a closed issue where nobody will see it
#   stale miss  a just-created issue does not list at all, so the red path
#               files a duplicate
#
# So: retry an empty result a few times, and confirm a hit against the issue
# itself, which is read-your-writes consistent. Real runs are minutes apart and
# would not race, but a re-run of a failed workflow is seconds apart and does.
open_issue_for_label() {
  attempt=1
  while [ "$attempt" -le 3 ]; do
    candidate="$(gh issue list --label "$1" --state open --limit 1 --json number --jq '.[0].number' 2>/dev/null || true)"
    if [ -n "$candidate" ]; then
      state="$(gh issue view "$candidate" --json state --jq .state 2>/dev/null || true)"
      [ "$state" = OPEN ] || return 0
      printf '%s' "$candidate"
      return 0
    fi
    if [ "$attempt" -lt 3 ]; then sleep 3; fi
    attempt=$((attempt + 1))
  done
  return 0
}

existing="$(open_issue_for_label "$LABEL")"

if [ "$verdict" = recovered ]; then
  if [ -n "$existing" ]; then
    gh issue comment "$existing" --body "Recovered — [this run]($RUN_URL) is green. Closing automatically."
    gh issue close "$existing"
    say "ci-alert: closed #$existing"
  else
    say "ci-alert: green, nothing open."
  fi
  exit 0
fi

# --- failing ----------------------------------------------------------------

body="\`$TOPIC\` failed on \`main\`.

- Run: $RUN_URL
- Job results: \`$RESULTS\`

The Pages deploy is **not** a required status check — it runs on push to \`main\`,
after the PR has merged — so nothing else reports this. Reproduce the published-site
half locally with \`make smoke-web\`.

This issue closes itself when a run of the same workflow goes green."

if [ -n "$existing" ]; then
  gh issue comment "$existing" --body "Still failing — [another run]($RUN_URL) went red. Job results: \`$RESULTS\`."
  say "ci-alert: commented on #$existing"
  exit 0
fi

# --force so a re-run after someone deletes the label still works, and so this
# does not need a separate bootstrap step on a fresh clone of the repo.
gh label create "$LABEL" --color b60205 --description "Opened automatically by scripts/ci-alert.sh" --force >/dev/null 2>&1 || true

gh issue create --title "$TITLE" --label "$LABEL" --body "$body" >&2
say "ci-alert: filed a new issue"
