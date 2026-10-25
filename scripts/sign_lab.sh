#!/usr/bin/env bash
# Sign Lab: sign at the Mac webcam into a local backend that drafts with the real
# composer (Groq) and speaks with the real voice (Sarvam on the Mac speakers).
# Nothing is dialled: the scripted receptionist answers the local "call".
#
#   scripts/sign_lab.sh                      Groq drafts + Sarvam voice (small cost)
#   scripts/sign_lab.sh --free               template drafts, no voice, no cost
#   scripts/sign_lab.sh --model asl          the public ASL Signs model with the open-set rule (D8):
#                                            no references, no SignCLIP download; needs
#                                            artifacts/asl_signs/{model.tflite,.venv} (asl-model-probe.md)
#   scripts/sign_lab.sh --bundle PATH        recognition bundle
#                                            (signclip default: the calibrated recognition-bundle-signclip.json,
#                                            else the provisional try bundle from export-bundle --provisional;
#                                            asl default: fixtures/asl/asl-bundle-provisional.json)
#   scripts/sign_lab.sh --camera N           webcam index (default 0)
#   scripts/sign_lab.sh --port N             backend port (default 8000)
#   scripts/sign_lab.sh --env-file PATH      where the Groq/Sarvam keys are (default: repo .env)
#   scripts/sign_lab.sh --recognition-dir D  spikes/recognition holding the venvs and bundle
#                                            (e.g. the main checkout when run from a worktree)
#   scripts/sign_lab.sh --backend-only [--receptionist manual]
#                                            only the backend, in this terminal; manual = you
#                                            type the receptionist's lines
#   scripts/sign_lab.sh --bridge-only        only the webcam bridge, against a running backend
#   scripts/sign_lab.sh ... -- ARGS          extra mac_bridge.py args, e.g. -- --replay-videos DIR
#
# Ctrl-C stops both processes.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
HOST=127.0.0.1
APP_TOKEN_VALUE=ishara-local-demo
CONTACT=clinic
HEALTH_WAIT_S=90

usage() {
  sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'
}

die() {
  echo "sign_lab: $*" >&2
  exit 1
}

port=8000
camera=0
model=signclip
bundle=""
env_file=""
recognition_dir="$ROOT/spikes/recognition"
mode=both
receptionist=script
paid=1
bridge_extra=()

need_value() {
  [[ $# -ge 2 && -n $2 ]] || { echo "sign_lab: $1 needs a value" >&2; exit 2; }
}

while (($#)); do
  case $1 in
    --free) paid=0 ;;
    --model) need_value "$@"; model=$2; shift ;;
    --bundle) need_value "$@"; bundle=$2; shift ;;
    --camera) need_value "$@"; camera=$2; shift ;;
    --port) need_value "$@"; port=$2; shift ;;
    --env-file) need_value "$@"; env_file=$2; shift ;;
    --recognition-dir) need_value "$@"; recognition_dir=$2; shift ;;
    --receptionist) need_value "$@"; receptionist=$2; shift ;;
    --backend-only) mode=backend ;;
    --bridge-only) mode=bridge ;;
    --) shift; bridge_extra=("$@"); break ;;
    -h | --help) usage; exit 0 ;;
    *) echo "sign_lab: unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
  shift
done

[[ $port =~ ^[0-9]+$ ]] || { echo "sign_lab: --port must be a number" >&2; exit 2; }
[[ $camera =~ ^[0-9]+$ ]] || { echo "sign_lab: --camera must be a number" >&2; exit 2; }
case $receptionist in
  script | manual) ;;
  *) echo "sign_lab: --receptionist must be script or manual" >&2; exit 2 ;;
esac
case $model in
  signclip | asl) ;;
  *) echo "sign_lab: --model must be signclip or asl" >&2; exit 2 ;;
esac

if [[ $receptionist == manual && $mode != backend ]]; then
  cat >&2 <<EOF
sign_lab: --receptionist manual reads her lines from the terminal, and the bridge needs
it too for SEND. Use two terminals:
  1) scripts/sign_lab.sh --backend-only --receptionist manual
  2) scripts/sign_lab.sh --bridge-only
EOF
  exit 2
fi

recognition_dir=$(cd "$recognition_dir" 2>/dev/null && pwd) ||
  die "no recognition folder at $recognition_dir; pass --recognition-dir"
if [[ -z $bundle && $model == signclip ]]; then
  # Prefer the calibrated bundle; before the calibration session exists, fall back to the
  # provisional try bundle (live_source flags it as PROVISIONAL on every result).
  bundle=$recognition_dir/artifacts/evidence/recognition-bundle-signclip.json
  provisional=$recognition_dir/artifacts/evidence/recognition-bundle-signclip-provisional.json
  [[ -f $bundle || ! -f $provisional ]] || bundle=$provisional
elif [[ -z $bundle ]]; then
  bundle=$recognition_dir/fixtures/asl/asl-bundle-provisional.json
fi
base_url="http://$HOST:$port"
signclip_python="$recognition_dir/artifacts/signclip/.venv/bin/python"
# The ASL model needs only MediaPipe (the recognition .venv) plus its own small LiteRT venv.
recognizer_python=$signclip_python
[[ $model == signclip ]] || recognizer_python="$recognition_dir/.venv/bin/python"
asl_python="$recognition_dir/artifacts/asl_signs/.venv/bin/python"
asl_model="$recognition_dir/artifacts/asl_signs/model.tflite"
bridge_python="$recognition_dir/artifacts/bridge/.venv/bin/python"

backend_args=(--port "$port" --app-token "$APP_TOKEN_VALUE" --receptionist "$receptionist")
if ((paid)); then
  backend_args+=(--composer groq --voice sarvam)
fi
if [[ -n $env_file ]]; then
  backend_args+=(--env-file "$env_file")
fi

# ---- preflight: everything is checked before anything starts ----

check_backend_tools() {
  command -v uv >/dev/null || die "uv is not installed: brew install uv"
  command -v curl >/dev/null || die "curl is not installed"
}

check_bridge_parts() {
  local problems=()
  if [[ ! -x $bridge_python ]]; then
    problems+=("no bridge venv at $bridge_python. Fix:
    cd $recognition_dir && uv venv --python 3.11 artifacts/bridge/.venv && \\
      uv pip install --python artifacts/bridge/.venv/bin/python --require-hashes -r requirements-bridge.lock")
  fi
  if [[ $model == signclip && ! -x $signclip_python ]]; then
    problems+=("no SignCLIP venv at $signclip_python. Fix (about 2.4 GB download):
    cd $recognition_dir && mkdir -p artifacts/signclip && uv venv --python 3.11 artifacts/signclip/.venv && \\
      uv pip install --python artifacts/signclip/.venv/bin/python -r requirements-signclip.txt && \\
      artifacts/signclip/.venv/bin/python setup_signclip.py")
  fi
  if [[ $model == asl && ! -x $recognizer_python ]]; then
    problems+=("no recognition venv at $recognizer_python (spikes/recognition/README.md: Set up)")
  fi
  if [[ $model == asl && ( ! -x $asl_python || ! -f $asl_model ) ]]; then
    problems+=("no ASL model at $asl_model with its venv at $asl_python. Fix (11 MB download):
    see docs/experiments/asl-model-probe.md, Reproduce (curl the model + class map, python3 -m venv, pip install ai-edge-litert numpy)")
  fi
  if [[ $model == signclip && ! -f $bundle ]]; then
    problems+=("no recognition bundle at $bundle. Fix: record and calibrate (spikes/recognition/README.md), then
    cd $recognition_dir && artifacts/signclip/.venv/bin/python retrieval.py calibrate --encoder signclip && \\
      artifacts/signclip/.venv/bin/python retrieval.py export-bundle --encoder signclip
  or pass --bundle PATH, or use --model asl.")
  fi
  if [[ $model == asl && ! -f $bundle ]]; then
    problems+=("no ASL bundle at $bundle; pass --bundle PATH")
  fi
  if [[ ! -f $recognition_dir/mac_bridge.py ]]; then
    problems+=("no mac_bridge.py in $recognition_dir; pass --recognition-dir")
  fi
  if ((${#problems[@]})); then
    printf 'sign_lab: %s\n' "${problems[@]}" >&2
    exit 1
  fi
}

backend_is_up() {
  curl -fsS --max-time 1 "$base_url/health" >/dev/null 2>&1
}

# ---- processes ----

backend_pid=""

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  if [[ -n $backend_pid ]] && kill -0 "$backend_pid" 2>/dev/null; then
    echo "sign_lab: stopping the backend"
    kill -TERM "$backend_pid" 2>/dev/null || true
    wait "$backend_pid" 2>/dev/null || true
  fi
  exit "$status"
}

run_backend_here() {
  cd "$ROOT/backend"
  exec uv run --quiet python -m scripts.sign_lab "${backend_args[@]}"
}

start_backend() {
  backend_is_up && die "something already answers on $base_url; stop it or pass --port"
  # Its lines are prefixed so they read apart from the bridge's in one terminal.
  (cd "$ROOT/backend" && exec uv run --quiet python -m scripts.sign_lab "${backend_args[@]}") \
    </dev/null > >(awk '{ print "[lab] " $0; fflush() }') 2>&1 &
  backend_pid=$!
  trap cleanup EXIT
  trap 'exit 130' INT TERM
  local waited=0
  until backend_is_up; do
    kill -0 "$backend_pid" 2>/dev/null ||
      die "the backend stopped during startup (see the [lab] lines above)"
    ((waited < HEALTH_WAIT_S * 4)) || die "the backend did not answer $base_url/health in ${HEALTH_WAIT_S} s"
    sleep 0.25
    waited=$((waited + 1))
  done
}

run_bridge() {
  # --live sits in the array so it is never empty (bash 3.2 + set -u).
  local source_args=(--live --camera "$camera") arg
  for arg in ${bridge_extra[@]+"${bridge_extra[@]}"}; do
    [[ $arg == --replay-videos ]] && source_args=(--live)
  done
  echo
  echo "sign_lab: starting the webcam bridge with --contact $CONTACT --confirm-cost."
  echo "  That flag only asks this local backend to start its scripted call: nothing is"
  echo "  dialled and the call is free. The only costs are Groq drafts and Sarvam audio"
  echo "  (none with --free). Rest your hands for 2 s, sign, then press s to SEND."
  echo
  cd "$recognition_dir"
  APP_TOKEN=$APP_TOKEN_VALUE "$bridge_python" mac_bridge.py --base-url "$base_url" \
    --contact "$CONTACT" --confirm-cost "${source_args[@]}" --model "$model" --bundle "$bundle" \
    --recognizer-python "$recognizer_python" ${bridge_extra[@]+"${bridge_extra[@]}"}
}

case $mode in
  backend)
    check_backend_tools
    run_backend_here
    ;;
  bridge)
    check_bridge_parts
    command -v curl >/dev/null || die "curl is not installed"
    backend_is_up ||
      die "no backend at $base_url. Start it first: scripts/sign_lab.sh --backend-only"
    run_bridge
    ;;
  both)
    check_backend_tools
    check_bridge_parts
    start_backend
    run_bridge
    ;;
esac
