#!/usr/bin/env bash
# Sign videos in, spoken sentences out: every call flow through the iOS app in the simulator
# and the free local backend (no Bolna, no Groq, nothing dialled). Each flow runs one
# IsharaUITests/VideoToSpeechUITests test against its own local_demo server.
#
#   IOS_DESTINATION="platform=iOS Simulator,id=<udid>" scripts/e2e_video_to_speech.sh [flow ...]
#
# Flows: live, attended, open-question, unattended (default: all four).
# Needs backend/.venv (cd backend && uv sync), the models in ios/Ishara/LocalAssets and a
# labelled clip set (ios/Ishara/LocalAssets/README.md). Optional overrides:
#   E2E_SOURCE_CLIPS  folder with the T04 replay set (default ios/Ishara/LocalAssets/SampleSigns)
#   E2E_CLIPS         a ready folder of clips named by sign instead (see VideoToSpeechUITests)
#   E2E_PORT (8799), E2E_DELAY (1.0, scales the receptionist's pauses), E2E_OUT (logs, results)
# ios/Ishara/Config/Secrets.xcconfig points at the local server during the run and is put
# back afterwards.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

case "${1:-}" in
  -h | --help) sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
esac

: "${IOS_DESTINATION:?set IOS_DESTINATION to your own simulator, e.g. platform=iOS Simulator,id=<udid>}"
PORT=${E2E_PORT:-8799}
DELAY=${E2E_DELAY:-1.0}
OUT=${E2E_OUT:-${TMPDIR:-/tmp}/ishara-e2e-$(date +%Y%m%d-%H%M%S)}
DERIVED=${E2E_DERIVED_DATA:-${TMPDIR:-/tmp}/ishara-e2e-derived}
PYTHON=${PYTHON:-$ROOT/backend/.venv/bin/python}
SECRETS=ios/Ishara/Config/Secrets.xcconfig
export DEVELOPER_DIR=${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}

flow_test() {
  case $1 in
    live) echo testLiveCallSignedFromVideosSpeaksExactlyEachApprovedDraft ;;
    attended) echo testAttendedCallForMeAnsweredBySignVideo ;;
    open-question) echo testOpenTimeQuestionAnsweredBySignVideos ;;
    unattended) echo testUnattendedCallForMeComesBackAsACallback ;;
    *) return 1 ;;
  esac
}

flow_receptionist() {
  case $1 in
    live) echo clinic ;;
    attended | unattended) echo offer ;;
    open-question) echo open-question ;;
  esac
}

flows=("$@")
((${#flows[@]})) || flows=(live attended open-question unattended)
for flow in "${flows[@]}"; do
  flow_test "$flow" >/dev/null || { echo "unknown flow: $flow (live, attended, open-question, unattended)" >&2; exit 2; }
done

[[ -x $PYTHON ]] || { echo "no backend venv at $PYTHON: cd backend && uv sync" >&2; exit 1; }
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "port $PORT is taken (another worktree's server?): set E2E_PORT" >&2
  exit 1
fi
mkdir -p "$OUT"

# Clips named by sign, picked from the T04 replay set: each one gives its sign in the app.
clips=${E2E_CLIPS:-}
if [[ -z $clips ]]; then
  source_clips=${E2E_SOURCE_CLIPS:-$ROOT/ios/Ishara/LocalAssets/SampleSigns}
  clips=$OUT/clips
  mkdir -p "$clips"
  while read -r from to; do
    [[ -f $source_clips/$from ]] || { echo "missing clip $source_clips/$from" >&2; exit 1; }
    cp "$source_clips/$from" "$clips/$to"
  done <<'EOF'
rest.mov rest.mov
hello_lp1.mp4 hello.mp4
no_lp1.mp4 no.mp4
tomorrow_lp1.mp4 tomorrow.mp4
please_lp1.mp4 please.mp4
yes_lp1.mp4 yes.mp4
thankyou_lp1_portrait.mp4 thankyou.mp4
none_name.mp4 none_oov.mp4
none_rest.mp4 none_rest.mp4
EOF
fi

# Point the app at the local server for the build; put the real file back on any exit.
backup=$(mktemp)
had_secrets=0
if [[ -f $SECRETS ]]; then
  cp "$SECRETS" "$backup"
  had_secrets=1
fi
server_pid=
# Stops the server and puts the real Secrets.xcconfig back; safe to run twice.
restore() {
  if [[ -n $server_pid ]]; then kill "$server_pid" 2>/dev/null || true; fi
  if [[ -f $backup ]]; then
    if ((had_secrets)); then cp "$backup" "$SECRETS"; else rm -f "$SECRETS"; fi
    rm -f "$backup"
  fi
}
trap restore EXIT
trap 'exit 130' INT TERM
cat >"$SECRETS" <<EOF
// Written by scripts/e2e_video_to_speech.sh for this run; the original is restored after it.
ISHARA_BACKEND_URL = http:/\$()/127.0.0.1:$PORT
ISHARA_APP_TOKEN = ishara-local-demo
EOF

xcode=(-project ios/Ishara.xcodeproj -scheme Ishara -destination "$IOS_DESTINATION" -derivedDataPath "$DERIVED")
echo "==> building for testing (log: $OUT/build.log)"
xcodebuild build-for-testing "${xcode[@]}" >"$OUT/build.log" 2>&1 || { tail -20 "$OUT/build.log"; exit 1; }

results=()
failed=0
for flow in "${flows[@]}"; do
  test_name=$(flow_test "$flow")
  receptionist=$(flow_receptionist "$flow")
  server_log=$OUT/$flow-server.log
  echo "==> $flow: local_demo --receptionist $receptionist, then $test_name"
  (cd backend && exec "$PYTHON" -m scripts.local_demo --port "$PORT" --delay "$DELAY" \
    --receptionist "$receptionist" >"$server_log" 2>&1) &
  server_pid=$!
  for _ in $(seq 50); do
    curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break
    sleep 0.2
  done
  status=PASS
  TEST_RUNNER_ISHARA_LOCAL_BACKEND=1 TEST_RUNNER_ISHARA_LOCAL_BACKEND_LOG="$server_log" \
    TEST_RUNNER_ISHARA_E2E_CLIPS="$clips" \
    xcodebuild test-without-building "${xcode[@]}" -resultBundlePath "$OUT/$flow.xcresult" \
    -only-testing:"IsharaUITests/VideoToSpeechUITests/$test_name" >"$OUT/$flow-test.log" 2>&1 || status=FAIL
  # A skipped test is not a pass (wrong server script, missing environment).
  if [[ $status == PASS ]] && ! grep -q "Executed 1 test, with 0 failures" "$OUT/$flow-test.log"; then
    status=FAIL
  fi
  if grep -q "skipped" "$OUT/$flow-test.log"; then status=SKIPPED; fi
  kill "$server_pid" 2>/dev/null || true
  wait "$server_pid" 2>/dev/null || true
  server_pid=
  [[ $status == PASS ]] || failed=1
  results+=("$flow: $status")
  grep -E ' \| [0-9.]+ s$' "$OUT/$flow-test.log" | sed 's/^/    /' || true
  echo "  $status"
done

restore
echo
echo "e2e video to speech (results and logs in $OUT):"
printf '  %s\n' "${results[@]}"
exit "$failed"
