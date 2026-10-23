#!/usr/bin/env bash
# Copy backend settings from the repo-root .env to a Heroku app's config vars.
# Only names listed in .env.example are sent, never HEROKU_* (local tooling only).
# Values are never printed; empty values are skipped, not unset.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
ENV_FILE=$ROOT/.env
EXAMPLE_FILE=$ROOT/.env.example
# shellcheck source=SCRIPTDIR/heroku_common.sh
source "$SCRIPT_DIR/heroku_common.sh"

usage() {
  cat <<'EOF'
Usage: backend/scripts/heroku_config_push.sh --app NAME [--yes]

Sets the Heroku config vars named in .env.example from the repo-root .env.
Without --yes it only lists which names would be set or skipped.
Setting config vars restarts the app's dynos.
EOF
}

# Names declared in .env.example (KEY= lines), minus HEROKU_*.
example_names() {
  local line name
  while IFS= read -r line || [[ -n $line ]]; do
    [[ $line =~ ^([A-Za-z_][A-Za-z0-9_]*)= ]] || continue
    name=${BASH_REMATCH[1]}
    [[ $name == HEROKU_* ]] && continue
    echo "$name"
  done <"$EXAMPLE_FILE"
}

# Value of the last NAME= line in .env, with one pair of surrounding quotes removed.
# The file is parsed, never sourced, so nothing in it is executed.
env_value() {
  local name=$1 line value=""
  while IFS= read -r line || [[ -n $line ]]; do
    line=${line%$'\r'}
    line=${line#export }
    [[ $line == "$name="* ]] && value=${line#"$name="}
  done <"$ENV_FILE"
  if ((${#value} >= 2)) && [[ ($value == \"*\" && $value == *\") || ($value == \'*\' && $value == *\') ]]; then
    value=${value:1:${#value}-2}
  fi
  printf '%s' "$value"
}

parse_heroku_args "$@"
((${#EXTRA_ARGS[@]} == 0)) || die "unknown option: ${EXTRA_ARGS[0]}"
[[ -f $EXAMPLE_FILE ]] || die "missing $EXAMPLE_FILE"
[[ -f $ENV_FILE ]] || die "missing $ENV_FILE (copy .env.example and fill it in)"

to_set=()
empty=()
while IFS= read -r name; do
  if [[ -n $(env_value "$name") ]]; then
    to_set+=("$name")
  else
    empty+=("$name")
  fi
done < <(example_names)

echo "app: $APP"
echo "will set: ${to_set[*]:-(none)}"
echo "empty in .env, skipped: ${empty[*]:-(none)}"

if ((YES == 0)); then
  echo "Dry run: nothing sent. Re-run with --yes to set these config vars." >&2
  exit 1
fi
((${#to_set[@]})) || die "nothing to set"
require_heroku

# NAME=value pairs go through a NUL-separated pipe into xargs, so values never pass through
# the shell's word splitting or the terminal. The CLI echoes the values it set; discard that.
for name in "${to_set[@]}"; do
  printf '%s=%s\0' "$name" "$(env_value "$name")"
done | xargs -0 heroku config:set --app "$APP" >/dev/null

echo "Set ${#to_set[@]} config vars on $APP."
