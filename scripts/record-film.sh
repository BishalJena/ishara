#!/usr/bin/env bash
# Records the launch film's demo (docs/demo/video/SCRIPT.md §5) from the real app.
#
#   scripts/record-film.sh <simulator-udid>
#
# Expects the app's tests built for that simulator into /tmp/ishara-film-dd:
#   xcodebuild -project ios/Ishara.xcodeproj -scheme Ishara -destination id=<udid> \
#     -derivedDataPath /tmp/ishara-film-dd build-for-testing
# and "Health history.pdf" (video/assets) in the simulator's Files, On My iPhone.
# Writes video/raw/app.mp4, video/raw/film-timeline.jsonl and video/raw/recording.json.
# The call is the scripted film call: nothing is dialled, no backend is used.
set -euo pipefail

sim=${1:?usage: scripts/record-film.sh <simulator-udid>}
repo=$(cd "$(dirname "$0")/.." && pwd)
raw="$repo/video/raw"
mkdir -p "$raw"

# A fresh install: no saved name, no recent calls, no old timeline.
xcrun simctl uninstall "$sim" ai.ishara.demo 2>/dev/null || true
xcrun simctl status_bar "$sim" override --time "9:41" --dataNetwork wifi --wifiMode active --wifiBars 3 \
  --cellularMode active --cellularBars 4 --operatorName "" --batteryState charged --batteryLevel 100

rm -f "$raw/app.mp4"
xcrun simctl io "$sim" recordVideo --codec=h264 --force "$raw/app.mp4" 2>"$raw/record.log" &
recorder=$!
# recordVideo prints "Recording started" once frames are being written.
for _ in $(seq 1 100); do
  grep -q "Recording started" "$raw/record.log" 2>/dev/null && break
  sleep 0.05
done
started=$(python3 -c 'import time; print(time.time())')

set +e
TEST_RUNNER_ISHARA_FILM=1 xcodebuild test-without-building -project "$repo/ios/Ishara.xcodeproj" -scheme Ishara \
  -destination "id=$sim" -derivedDataPath /tmp/ishara-film-dd \
  -only-testing:IsharaUITests/FilmRecordingUITests 2>&1 | grep -E "error:|Test Case|TEST (SUCCEEDED|FAILED)"
status=${PIPESTATUS[0]}
set -e

kill -INT "$recorder"
wait "$recorder" 2>/dev/null || true

container=$(xcrun simctl get_app_container "$sim" ai.ishara.demo data)
cp "$container/tmp/film-timeline.jsonl" "$raw/film-timeline.jsonl"
printf '{"recordingStartedAt": %s}\n' "$started" >"$raw/recording.json"
echo "recorded: $raw/app.mp4 ($(du -h "$raw/app.mp4" | cut -f1)), $(wc -l <"$raw/film-timeline.jsonl") timeline events, test status $status"
exit "$status"
