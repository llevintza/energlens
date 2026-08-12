#!/usr/bin/env sh
# Assert that the deployed Pages site actually loads.
#
#   scripts/smoke-pages.sh                 check the live site (URL from the Pages API)
#   scripts/smoke-pages.sh <url>           check that URL instead
#
# `npm run build` succeeding proves nothing about the published site: the base
# path and API_URL are inlined at build time, so a wrong VITE_BASE compiles
# cleanly and only 404s once served. That is exactly what shipped in PR #1 —
# index.html returned 200 while every asset under it 404'd, leaving a blank
# #root — and no build-time check can catch it by construction. This asserts
# against the deployed URL instead: the page loads, the bundle it references
# sits under the base path the site is served from, and that bundle responds.
#
# Every failure path prints the command that fixes it (issue #2, principle 5).
set -eu

say() { printf '%s\n' "$*" >&2; }
die() { printf '%s\n' "$*" >&2; exit 1; }

REDEPLOY='Fix: gh workflow run "Deploy frontend to GitHub Pages"'

# --- resolve the URL -------------------------------------------------------

# Asked from the API rather than hardcoded, so a repo rename or a custom domain
# is picked up for free — the same reason deploy-frontend.yml reads the base
# path from actions/configure-pages instead of spelling it out.
resolve_url() {
  if [ -n "${GITHUB_REPOSITORY:-}" ]; then
    gh api "repos/$GITHUB_REPOSITORY/pages" --jq .html_url 2>/dev/null && return 0
  else
    gh api "repos/{owner}/{repo}/pages" --jq .html_url 2>/dev/null && return 0
  fi
  return 1
}

URL="${1:-}"
if [ -z "$URL" ]; then
  command -v gh >/dev/null 2>&1 || die "error: no URL given and no gh on PATH to look one up.
     Fix: scripts/smoke-pages.sh https://<owner>.github.io/<repo>/"
  URL="$(resolve_url || true)"
  [ -n "$URL" ] || die "error: could not read the Pages URL from the GitHub API.
     Locally  : gh is not authenticated, or Pages is not enabled on this repo.
                Fix: gh auth login   (or pass one: make smoke-web URL=https://…)
     In CI    : the job is missing GH_TOKEN or 'permissions: pages: read'."
fi

case "$URL" in
  http://*|https://*) ;;
  *) die "error: '$URL' is not an absolute http(s) URL.
     Fix: make smoke-web URL=https://<owner>.github.io/<repo>/" ;;
esac

# Split into origin and base path. Both are needed: a root-absolute asset
# resolves against the origin, a relative one against the base.
ORIGIN="$(printf '%s' "$URL" | sed -E 's#^(https?://[^/]+).*#\1#')"
BASE="${URL#"$ORIGIN"}"
BASE="${BASE%%\?*}"
case "$BASE" in
  ''|*[!/]) BASE="$BASE/" ;;
esac

say "smoke: $ORIGIN$BASE"

# --- fetch the page --------------------------------------------------------

# --retry covers CDN propagation in the seconds after deploy-pages returns.
# The cache-buster is the load-bearing part: without it a stale edge copy of
# index.html would let a broken deploy pass by validating the *previous*
# bundle, which is a false green — the one outcome this check must not produce.
fetch() {
  curl -fsSL --max-time 20 --retry 5 --retry-delay 3 --retry-all-errors "$1"
}

STAMP="$(date +%s)"
HTML="$(fetch "$ORIGIN$BASE?smoke=$STAMP")" || die "error: GET $ORIGIN$BASE did not return 200.
     The site is not serving at all — check the Pages settings and the last deploy.
     $REDEPLOY"

case "$HTML" in
  *'id="root"'*) ;;
  *) die "error: $ORIGIN$BASE returned 200 but has no <div id=\"root\"> — this is not the SPA.
     A stray README render or a 404 page can answer 200 here.
     $REDEPLOY" ;;
esac

# --- check every asset the page references ---------------------------------

# The module script is mandatory; the stylesheet is not emitted by every build,
# so it is checked only when present.
ASSETS="$(printf '%s' "$HTML" \
  | grep -oE '(src|href)="[^"]+\.(js|css)"' \
  | sed -E 's/^(src|href)="//; s/"$//' \
  || true)"

case "$ASSETS" in
  *.js*) ;;
  *) die "error: $ORIGIN$BASE references no JavaScript bundle.
     The published index.html is not a Vite build output.
     $REDEPLOY" ;;
esac

for asset in $ASSETS; do
  case "$asset" in
    http://*|https://*)
      target="$asset" ;;
    "$BASE"*)
      target="$ORIGIN$asset" ;;
    /*)
      # Root-absolute but outside the base the site is served from: the deployed
      # bundle was built with the wrong VITE_BASE. This is the PR #1 defect, and
      # naming both paths is the difference between a diagnosis and a bare 404.
      die "error: stale base path in the deployed bundle.
     Served from : $BASE
     References  : $asset
     The live build has the wrong VITE_BASE. It comes from actions/configure-pages,
     so a redeploy picks up the current one.
     $REDEPLOY" ;;
    *)
      target="$ORIGIN$BASE$asset" ;;
  esac

  curl -fsS -o /dev/null --max-time 20 --retry 3 --retry-delay 3 --retry-all-errors "$target" \
    || die "error: $target did not return 200, but $ORIGIN$BASE references it.
     The page loads and then renders nothing — assets 404 while the HTML is fine.
     $REDEPLOY"
  say "  ok  $target"
done

say "smoke: ok"
