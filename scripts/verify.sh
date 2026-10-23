#!/usr/bin/env bash
# Run every local check in one go and print a summary.
#
#   scripts/verify.sh               stop at the first failing category
#   scripts/verify.sh --keep-going  run every category, then report
#
# Categories that don't exist yet (no Swift packages, no Xcode project, no recognition venv)
# or need a missing tool (Xcode, shellcheck) are reported as SKIPPED with the reason.
# Optional overrides: IOS_SCHEME (default Ishara), IOS_DESTINATION (xcodebuild -destination).
set -uo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT" || exit 1

KEEP_GOING=0
case "${1:-}" in
  "") ;;
  --keep-going) KEEP_GOING=1 ;;
  -h | --help) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
esac

SKIP_FILE=$(mktemp)
trap 'rm -f "$SKIP_FILE"' EXIT

names=()
results=()
failed=0

# Called inside a category to stop it and record why it was skipped.
skip() {
  echo "$1" >"$SKIP_FILE"
  echo "  SKIPPED: $1"
  exit 0
}

step() {
  echo "  -> $*"
  "$@"
}

# Each category runs in a subshell with `set -e`, so the first failing command fails it.
run_category() {
  local name=$1 fn=$2 status reason
  if ((failed && !KEEP_GOING)); then
    names+=("$name")
    results+=("NOT RUN")
    return
  fi
  echo
  echo "==> $name"
  : >"$SKIP_FILE"
  (
    set -e
    "$fn"
  )
  status=$?
  reason=$(cat "$SKIP_FILE")
  names+=("$name")
  if ((status != 0)); then
    results+=("FAIL (exit $status)")
    failed=1
  elif [[ -n $reason ]]; then
    results+=("SKIPPED: $reason")
  else
    results+=("PASS")
  fi
}

# Xcode (not just the Command Line Tools) is needed for XCTest and simulators. Use an
# explicit DEVELOPER_DIR, else the selected Xcode, else the first /Applications/Xcode*.app.
find_xcode() {
  local selected app
  if [[ -n ${DEVELOPER_DIR:-} && -x "$DEVELOPER_DIR/usr/bin/xcodebuild" ]]; then
    echo "$DEVELOPER_DIR"
    return
  fi
  selected=$(xcode-select -p 2>/dev/null || true)
  if [[ $selected == *.app/Contents/Developer ]]; then
    echo "$selected"
    return
  fi
  for app in /Applications/Xcode.app /Applications/Xcode*.app; do
    if [[ -x "$app/Contents/Developer/usr/bin/xcodebuild" ]]; then
      echo "$app/Contents/Developer"
      return
    fi
  done
}

XCODE_DIR=$(find_xcode)
if [[ -n $XCODE_DIR ]]; then
  export DEVELOPER_DIR=$XCODE_DIR
fi

check_backend() {
  [[ -f backend/pyproject.toml ]] || skip "no backend/pyproject.toml"
  command -v uv >/dev/null || { echo "  uv is required for the backend checks" >&2; exit 1; }
  cd backend
  step uv sync --locked --quiet
  step uv run --locked ruff format --check .
  step uv run --locked ruff check .
  step uv run --locked pytest -q
}

check_call_flow() {
  [[ -d spikes/call_flow ]] || skip "no spikes/call_flow"
  step python3 -m unittest discover -s spikes/call_flow -p 'test_*.py'
}

# test_retrieval needs numpy and cv2 only. The full README venv (.venv) or a light one built
# from requirements-light.txt (.venv-light) both work; test_mini needs torch and is not run.
check_recognition_light() {
  local python=""
  cd spikes/recognition 2>/dev/null || skip "no spikes/recognition"
  for candidate in .venv/bin/python .venv-light/bin/python; do
    if [[ -x $candidate ]]; then
      python=$candidate
      break
    fi
  done
  if [[ -z $python ]]; then
    echo "  to enable: cd spikes/recognition && uv venv --python 3.11 .venv-light" \
      "&& uv pip install --python .venv-light/bin/python -r requirements-light.txt"
    skip "no spikes/recognition/.venv or .venv-light"
  fi
  step "$python" -m unittest test_retrieval
}

check_shellcheck() {
  command -v shellcheck >/dev/null || skip "shellcheck not installed (brew install shellcheck)"
  local scripts=()
  for file in scripts/*.sh backend/scripts/*.sh; do
    [[ -f $file ]] && scripts+=("$file")
  done
  ((${#scripts[@]})) || skip "no shell scripts"
  step shellcheck "${scripts[@]}"
}

check_script_tests() {
  compgen -G "backend/scripts/test_*.py" >/dev/null || skip "no backend/scripts/test_*.py"
  step python3 -m unittest discover -s backend/scripts -p 'test_*.py'
}

check_swift_packages() {
  local manifests=() manifest
  for manifest in ios/Packages/*/Package.swift; do
    [[ -f $manifest ]] && manifests+=("$manifest")
  done
  ((${#manifests[@]})) || skip "no ios/Packages/*/Package.swift"
  [[ -n $XCODE_DIR ]] || skip "Xcode not found in /Applications (Command Line Tools have no XCTest)"
  for manifest in "${manifests[@]}"; do
    step swift test --package-path "$(dirname "$manifest")"
  done
}

# Prefer an available iPhone 17 simulator, else the first available iPhone.
pick_simulator() {
  local devices udid
  devices=$(xcrun simctl list devices available | grep -E '^[[:space:]]+iPhone')
  udid=$(grep -E '^[[:space:]]+iPhone 17 \(' <<<"$devices" | head -n 1 | grep -oE '[0-9A-F-]{36}')
  [[ -n $udid ]] || udid=$(head -n 1 <<<"$devices" | grep -oE '[0-9A-F-]{36}')
  echo "$udid"
}

check_ios_app() {
  local project=ios/Ishara.xcodeproj destination udid
  if [[ ! -d $project ]]; then
    [[ -f ios/project.yml ]] && skip "$project not generated (cd ios && xcodegen generate)"
    skip "no $project"
  fi
  [[ -n $XCODE_DIR ]] || skip "Xcode not found in /Applications"
  destination=${IOS_DESTINATION:-}
  if [[ -z $destination ]]; then
    udid=$(pick_simulator)
    [[ -n $udid ]] || { echo "  no available iPhone simulator; add an iOS runtime in Xcode" >&2; exit 1; }
    destination="platform=iOS Simulator,id=$udid"
  fi
  step xcodebuild test -quiet -project "$project" -scheme "${IOS_SCHEME:-Ishara}" \
    -destination "$destination"
}

echo "Xcode: ${XCODE_DIR:-not found}"
run_category "backend (format, lint, tests)" check_backend
run_category "call_flow tests" check_call_flow
run_category "recognition light tests" check_recognition_light
run_category "shellcheck" check_shellcheck
run_category "heroku script tests" check_script_tests
run_category "swift packages" check_swift_packages
run_category "ios app (xcodebuild test)" check_ios_app

echo
echo "Summary"
for i in "${!names[@]}"; do
  printf '  %-32s %s\n' "${names[$i]}" "${results[$i]}"
done

if ((failed)); then
  echo "verify: FAILED"
  exit 1
fi
echo "verify: OK"
