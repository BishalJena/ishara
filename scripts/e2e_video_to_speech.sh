#!/usr/bin/env bash
# Sign videos in, spoken sentences out: every call flow through the iOS app in the simulator.
# Each flow runs one IsharaUITests/VideoToSpeechUITests test.
#
#   IOS_DESTINATION="platform=iOS Simulator,id=<udid>" scripts/e2e_video_to_speech.sh [flow ...]
#       the free local backend (no Bolna, no Groq, nothing dialled), each flow against its
#       own local_demo server; the spoken text is read from the server log
#   ... scripts/e2e_video_to_speech.sh --real --flow <flow> --dry-run
#       prints the cost and the receptionist's script; builds, contacts and dials nothing
#   ... scripts/e2e_video_to_speech.sh --real --flow <flow> --confirm-cost
#       ONE real call: the deployed backend (the Secrets.xcconfig as it is) and real Bolna
#       dial the allowlisted contact; a person answers and says the lines printed as
#       "SAY NOW" prompts. Checked on the app's screen only
#   ... scripts/e2e_video_to_speech.sh --rehearse --flow <flow>
#       the --real test and prompts against local_demo, whose stand-in says the lines: free
#
# Flows: live, attended, open-question (or open), unattended (default: all four, local only).
# Needs backend/.venv (cd backend && uv sync), the models in ios/Ishara/LocalAssets and a
# labelled clip set (ios/Ishara/LocalAssets/README.md). Optional overrides:
#   E2E_SOURCE_CLIPS  folder with the T04 replay set (default ios/Ishara/LocalAssets/SampleSigns)
#   E2E_CLIPS         a ready folder of clips named by sign instead (see VideoToSpeechUITests)
#   E2E_PORT (8799), E2E_DELAY (1.0, scales the receptionist's pauses), E2E_OUT (logs, results)
#   E2E_HUMAN_WAIT    seconds the person may take to answer or say a line (90; --real, --rehearse)
# Locally ios/Ishara/Config/Secrets.xcconfig points at the local server during the run and is
# put back afterwards; --real leaves it alone and refuses one that points at this Mac.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

mode=local
dry_run=0
confirm_cost=0
flows=()
while (($#)); do
  case $1 in
    -h | --help) sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    --real) mode=real ;;
    --rehearse) mode=rehearse ;;
    --dry-run) dry_run=1 ;;
    --confirm-cost) confirm_cost=1 ;;
    --flow)
      (($# > 1)) || { echo "--flow needs a flow name" >&2; exit 2; }
      flows+=("$2")
      shift
      ;;
    -*) echo "unknown option: $1 (see --help)" >&2; exit 2 ;;
    *) flows+=("$1") ;;
  esac
  shift
done

flow_test() {
  case $1 in
    live) echo testLiveCallSignedFromVideosSpeaksExactlyEachApprovedDraft ;;
    attended) echo testAttendedCallForMeAnsweredBySignVideo ;;
    open-question) echo testOpenTimeQuestionAnsweredBySignVideos ;;
    unattended) echo testUnattendedCallForMeComesBackAsACallback ;;
    *) return 1 ;;
  esac
}

# The stand-in receptionist's script in local_demo for each flow.
flow_receptionist() {
  case $1 in
    live) echo clinic ;;
    attended | unattended) echo offer ;;
    open-question) echo open-question ;;
  esac
}

# What the person answering a real call says, in order (the 28 Oct live-call lines).
flow_lines() {
  case $1 in
    live) printf '%s\n' "We have 4 pm tomorrow. Does that work?" "Yes, 10:30 tomorrow morning." ;;
    attended | unattended) printf '%s\n' "We have 4 pm tomorrow. Does that work?" ;;
    open-question) printf '%s\n' "What time would you like to come in?" "We have 4 pm tomorrow. Does that work?" ;;
  esac
}

# When they say it; the test prints the same steps as "SAY NOW" prompts during the call.
flow_plan() {
  local opening="I'd like to book a doctor's appointment for Riya, tomorrow."
  echo "  1. The phone rings from Ishara's calling number (a Bolna number). Answer and say"
  echo "     nothing yet: you hear the disclosure (\"Hello, I'm calling for a Deaf caller ...\")."
  case $1 in
    live)
      echo "  2. The user signs HELLO and taps SEND; the voice says \"Hello.\"   -> SAY line 1"
      echo "  3. The user signs NO, a rest, an unknown sign, TOMORROW, PLEASE (about 30 s; you may"
      echo "     hear \"One moment please, I'm signing my reply.\"), taps SEND; the voice asks for"
      echo "     something tomorrow                                           -> SAY line 2"
      echo "  4. The user signs YES, THANK-YOU, SEND; the voice says it. Stay quiet: the app ends"
      echo "     the call (\"Thank you for your time. Goodbye.\")."
      ;;
    attended)
      echo "  2. The agent says \"$opening\"   -> SAY line 1"
      echo "  3. The agent says \"One moment, please.\"; the user signs YES within 10 s and the"
      echo "     agent says \"Yes, 4 pm tomorrow works. Thank you.\" Stay quiet: it hangs up (~10 s)."
      ;;
    open-question)
      echo "  2. The agent says \"$opening\"   -> SAY line 1"
      echo "  3. The agent says \"One moment, please.\"; the user signs TOMORROW and the agent says"
      echo "     \"Tomorrow, please. What times are available?\"              -> SAY line 2"
      echo "  4. \"One moment, please.\" again; the user signs YES and the agent says \"Yes, 4 pm"
      echo "     tomorrow works. Thank you.\" Stay quiet: it hangs up (~10 s)."
      ;;
    unattended)
      echo "  2. The agent says \"$opening\"   -> SAY line 1"
      echo "  3. The agent says it will call back, then hangs up. Stay quiet."
      ;;
  esac
}

flow_minutes() {
  case $1 in
    live) echo 3 ;;
    open-question) echo 2 ;;
    attended | unattended) echo 1-2 ;;
  esac
}

print_plan() {
  local flow=$1 n=0 line
  echo "Flow: $flow ($(flow_test "$flow"))"
  echo "The receptionist's lines:"
  while IFS= read -r line; do
    n=$((n + 1))
    echo "  line $n: \"$line\""
  done < <(flow_lines "$flow")
  echo "When:"
  flow_plan "$flow"
  echo "Up to ${E2E_HUMAN_WAIT:-90} s to answer and for each line; the 10 s question window starts when"
  echo "the receptionist's line is transcribed, so the test signs the answer straight away."
}

cost_line() {
  echo "COST: one real call through Bolna to the allowlisted contact (the verified phone): about"
  echo "      ₹5.5/min plus telephony, ~$(flow_minutes "$1") min here (≈ ₹10-30), plus a few Groq drafts."
}

((${#flows[@]})) || [[ $mode != local ]] || flows=(live attended open-question unattended)
for i in "${!flows[@]}"; do
  [[ ${flows[$i]} == open ]] && flows[i]=open-question
  flow_test "${flows[$i]}" >/dev/null || { echo "unknown flow: ${flows[$i]} (live, attended, open-question, unattended)" >&2; exit 2; }
done
if [[ $mode != local ]] && ((${#flows[@]} != 1)); then
  echo "--$mode runs exactly one flow: --flow live|attended|open-question|unattended" >&2
  exit 2
fi

if [[ $mode == real ]]; then
  cost_line "${flows[0]}"
  print_plan "${flows[0]}"
  if ((dry_run)); then
    echo
    echo "Dry run: nothing was built, contacted or dialled. For the call, add --confirm-cost instead of --dry-run."
    exit 0
  fi
  if ((!confirm_cost)); then
    echo "Refusing to dial without --confirm-cost." >&2
    exit 2
  fi
elif ((dry_run)); then
  for flow in "${flows[@]}"; do print_plan "$flow"; done
  echo "Dry run: nothing was built or started."
  exit 0
fi

: "${IOS_DESTINATION:?set IOS_DESTINATION to your own simulator, e.g. platform=iOS Simulator,id=<udid>}"
PORT=${E2E_PORT:-8799}
DELAY=${E2E_DELAY:-1.0}
HUMAN_WAIT=${E2E_HUMAN_WAIT:-90}
OUT=${E2E_OUT:-${TMPDIR:-/tmp}/ishara-e2e-$(date +%Y%m%d-%H%M%S)}
# The deployed build has other Secrets.xcconfig values: keep it apart from the local one.
if [[ $mode == real ]]; then
  DERIVED=${E2E_DERIVED_DATA:-${TMPDIR:-/tmp}/ishara-e2e-deployed-derived}
else
  DERIVED=${E2E_DERIVED_DATA:-${TMPDIR:-/tmp}/ishara-e2e-derived}
fi
PYTHON=${PYTHON:-$ROOT/backend/.venv/bin/python}
SECRETS=ios/Ishara/Config/Secrets.xcconfig
export DEVELOPER_DIR=${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}

if [[ $mode == real ]]; then
  [[ -f $SECRETS ]] || { echo "no $SECRETS: copy it from the main checkout (it points at the deployed backend)" >&2; exit 1; }
  # Read without printing: the values never reach the terminal or the logs.
  backend_url=$(sed -n 's/^[[:space:]]*ISHARA_BACKEND_URL[[:space:]]*=[[:space:]]*//p' "$SECRETS" | sed 's/[[:space:]]*$//')
  # xcconfig writes "//" as "/$()/" so it isn't read as a comment.
  backend_url=${backend_url//\$()/}
  case $backend_url in
    https://*) ;;
    *) echo "$SECRETS does not point at an https backend (an interrupted local run?); restore it from the main checkout" >&2; exit 1 ;;
  esac
  if [[ $backend_url == *127.0.0.1* || $backend_url == *localhost* ]]; then
    echo "$SECRETS points at this Mac; restore it from the main checkout" >&2
    exit 1
  fi
else
  [[ -x $PYTHON ]] || { echo "no backend venv at $PYTHON: cd backend && uv sync" >&2; exit 1; }
  if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "port $PORT is taken (another worktree's server?): set E2E_PORT" >&2
    exit 1
  fi
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

# Prints the test's prompts for the person on the phone as they come, with the time;
# stops (after the last lines) once "$1.done" exists.
show_prompts() {
  local file=$1 shown=0 total last=0
  while :; do
    [[ -f $file.done ]] && last=1
    total=$(wc -l <"$file")
    if ((total > shown)); then
      sed -n "$((shown + 1)),${total}p" "$file" | while IFS= read -r line; do
        printf '  [%s] %s\n' "$(date +%H:%M:%S)" "$line"
      done
      shown=$total
    fi
    ((last)) && return 0
    sleep 0.3
  done
}

backup=$(mktemp)
had_secrets=0
swapped=0
server_pid=
prompts_pid=
# Stops the server and the prompt printer and puts the real Secrets.xcconfig back; safe to run twice.
restore() {
  if [[ -n $server_pid ]]; then kill "$server_pid" 2>/dev/null || true; fi
  if [[ -n $prompts_pid ]]; then kill "$prompts_pid" 2>/dev/null || true; fi
  if [[ -f $backup ]]; then
    if ((swapped)); then
      if ((had_secrets)); then cp "$backup" "$SECRETS"; else rm -f "$SECRETS"; fi
    fi
    rm -f "$backup"
  fi
}
trap restore EXIT
trap 'exit 130' INT TERM

if [[ $mode != real ]]; then
  # Point the app at the local server for the build; put the real file back on any exit.
  if [[ -f $SECRETS ]]; then
    cp "$SECRETS" "$backup"
    had_secrets=1
  fi
  swapped=1
  cat >"$SECRETS" <<EOF
// Written by scripts/e2e_video_to_speech.sh for this run; the original is restored after it.
ISHARA_BACKEND_URL = http:/\$()/127.0.0.1:$PORT
ISHARA_APP_TOKEN = ishara-local-demo
EOF
fi

xcode=(-project ios/Ishara.xcodeproj -scheme Ishara -destination "$IOS_DESTINATION" -derivedDataPath "$DERIVED")
echo "==> building for testing (log: $OUT/build.log)"
xcodebuild build-for-testing "${xcode[@]}" >"$OUT/build.log" 2>&1 || { tail -20 "$OUT/build.log"; exit 1; }

if [[ $mode == real ]]; then
  # A sleeping or broken backend would mean a silent call: check before dialling.
  curl -fsS --max-time 20 "$backend_url/health" >/dev/null 2>&1 || { echo "the deployed backend's /health did not answer: not dialling" >&2; exit 1; }
  echo "==> deployed backend healthy"
fi

results=()
failed=0
for flow in "${flows[@]}"; do
  test_name=$(flow_test "$flow")
  test_env=(TEST_RUNNER_ISHARA_E2E_CLIPS="$clips")
  if [[ $mode == local || $mode == rehearse ]]; then
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
    test_env+=(TEST_RUNNER_ISHARA_LOCAL_BACKEND=1 TEST_RUNNER_ISHARA_LOCAL_BACKEND_LOG="$server_log")
  else
    echo "==> $flow: a real call, then $test_name"
  fi
  if [[ $mode != local ]]; then
    prompts=$OUT/$flow-prompts.txt
    : >"$prompts"
    lines=$(flow_lines "$flow" | paste -sd '|' -)
    test_env+=(TEST_RUNNER_ISHARA_E2E_BACKEND=deployed TEST_RUNNER_ISHARA_E2E_PROMPTS="$prompts"
      TEST_RUNNER_ISHARA_E2E_LINES="$lines" TEST_RUNNER_ISHARA_E2E_HUMAN_WAIT="$HUMAN_WAIT")
    echo "==> prompts for the person on the phone follow (also in $prompts); the call starts in ~30 s"
    show_prompts "$prompts" &
    prompts_pid=$!
  fi
  status=PASS
  env "${test_env[@]}" xcodebuild test-without-building "${xcode[@]}" -resultBundlePath "$OUT/$flow.xcresult" \
    -only-testing:"IsharaUITests/VideoToSpeechUITests/$test_name" >"$OUT/$flow-test.log" 2>&1 || status=FAIL
  if [[ -n $prompts_pid ]]; then
    touch "$prompts.done"
    wait "$prompts_pid" 2>/dev/null || true
    prompts_pid=
  fi
  # A skipped test is not a pass (wrong server script, missing environment).
  if [[ $status == PASS ]] && ! grep -q "Executed 1 test, with 0 failures" "$OUT/$flow-test.log"; then
    status=FAIL
  fi
  if grep -q "skipped" "$OUT/$flow-test.log"; then status=SKIPPED; fi
  if [[ -n $server_pid ]]; then
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
    server_pid=
  fi
  [[ $status == PASS ]] || failed=1
  results+=("$flow: $status")
  grep -E ' \| [0-9.]+ s$' "$OUT/$flow-test.log" | sed 's/^/    /' || true
  if [[ $status == FAIL ]]; then
    grep -E 'error: |Failure|failed -' "$OUT/$flow-test.log" | head -5 | sed 's/^/    /' || true
  fi
  echo "  $status"
done

restore
echo
echo "e2e video to speech, $mode (results and logs in $OUT):"
printf '  %s\n' "${results[@]}"
exit "$failed"
