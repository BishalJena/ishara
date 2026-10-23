#!/usr/bin/env bash
# Deploy the committed backend/ directory to a Heroku app and check /health.
# backend/ is pushed on its own with `git subtree split`, so Heroku sees pyproject.toml,
# uv.lock, .python-version and Procfile at the root and builds it with uv.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=SCRIPTDIR/heroku_common.sh
source "$SCRIPT_DIR/heroku_common.sh"

HEALTH_ATTEMPTS=${HEALTH_ATTEMPTS:-12}
HEALTH_DELAY=${HEALTH_DELAY:-5}

usage() {
  cat <<'EOF'
Usage: backend/scripts/heroku_deploy.sh --app NAME --yes

Pushes the committed backend/ tree (uncommitted changes are refused) to the
app's main branch, refuses Eco dynos (they sleep and Bolna would hear silence),
then prints the /health status and the names of missing config.
HEROKU_GIT_URL overrides the push target (default https://git.heroku.com/NAME.git).
EOF
}

# True when `heroku ps:type` lists any process type on an Eco dyno.
on_eco() {
  grep -Eiq '^[[:space:]]*[a-z0-9_-]+[[:space:]]+eco([[:space:]]|$)' <<<"${1//│/ }"
}

dyno_types() {
  heroku ps:type --app "$APP" || die "could not read dyno types for $APP (logged in? app exists?)"
}

parse_heroku_args "$@"
((${#EXTRA_ARGS[@]} == 0)) || die "unknown option: ${EXTRA_ARGS[0]}"
if ((YES == 0)); then
  usage >&2
  die "refusing to deploy without --yes"
fi
require_heroku
command -v python3 >/dev/null || die "python3 is needed to read the /health response"

ROOT=$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)
cd "$ROOT"
[[ -z $(git status --porcelain -- backend) ]] ||
  die "backend/ has uncommitted changes; commit them first (only committed code is deployed)"

types=$(dyno_types)
if on_eco "$types"; then
  die "$APP runs Eco dynos, which sleep. Run: heroku ps:type web=basic --app $APP"
fi

echo "Splitting backend/ from $(git rev-parse --short HEAD)..."
tree=$(git subtree split --prefix backend HEAD)
remote=${HEROKU_GIT_URL:-https://git.heroku.com/$APP.git}
# Force: each split is a fresh history, so it rarely fast-forwards what Heroku has.
git push --force "$remote" "$tree:refs/heads/main"

# A brand-new app has no dynos before its first build, so check again after the push.
types=$(dyno_types)
if on_eco "$types"; then
  die "deployed, but $APP is on Eco dynos. Run: heroku ps:type web=basic --app $APP"
fi

web_url=$(heroku info -s --app "$APP" | sed -n 's/^web_url=//p')
[[ -n $web_url ]] || die "could not find web_url for $APP"
health_url=${web_url%/}/health

body=""
for ((attempt = 1; attempt <= HEALTH_ATTEMPTS; attempt++)); do
  if body=$(curl -fsS --max-time 10 "$health_url" 2>/dev/null); then
    break
  fi
  body=""
  echo "waiting for /health ($attempt/$HEALTH_ATTEMPTS)..."
  sleep "$HEALTH_DELAY"
done
[[ -n $body ]] || die "/health did not answer; check: heroku logs --tail --app $APP"

# Print only status and missing_config names, nothing else from the response.
python3 -c '
import json, sys
health = json.loads(sys.argv[1])
missing = health.get("missing_config") or []
print("status:", health.get("status"))
print("missing_config:", ", ".join(missing) if missing else "none")
sys.exit(0 if health.get("status") == "ok" else 1)
' "$body"
