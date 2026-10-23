# shellcheck shell=bash
# shellcheck disable=SC2034 # APP, YES and EXTRA_ARGS are read by the sourcing script.
# Shared helpers for the Heroku scripts. Source it; don't run it.
# Callers define `usage` before calling parse_heroku_args.

APP=""
YES=0
EXTRA_ARGS=()

die() {
  echo "error: $*" >&2
  exit 1
}

# Parses --app NAME and --yes; anything else is left in EXTRA_ARGS for the caller.
parse_heroku_args() {
  while (($#)); do
    case $1 in
      --app)
        (($# >= 2)) || die "--app needs a value"
        APP=$2
        shift 2
        ;;
      --app=*)
        APP=${1#--app=}
        shift
        ;;
      --yes)
        YES=1
        shift
        ;;
      -h | --help)
        usage
        exit 0
        ;;
      *)
        EXTRA_ARGS+=("$1")
        shift
        ;;
    esac
  done
  [[ -n $APP ]] || { usage >&2; die "--app NAME is required"; }
  # Heroku app names: lowercase letter first, then letters, digits or dashes; 3-30 chars.
  [[ $APP =~ ^[a-z][a-z0-9-]{2,29}$ ]] || die "not a valid Heroku app name: $APP"
}

require_heroku() {
  command -v heroku >/dev/null || die "Heroku CLI not found; install it and run 'heroku login'"
}
