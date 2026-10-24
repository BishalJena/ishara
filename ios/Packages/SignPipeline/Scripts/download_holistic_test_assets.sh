#!/usr/bin/env bash
# Fetch what SignPipelineMediaPipeTests needs into TestAssets/ (gitignored):
# the Holistic Landmarker model and the photo MediaPipe's own iOS Holistic test
# uses (male_full_height_hands.jpg, ~56 KB). Its expected landmarks come from
# mediapipe/tasks/testdata/vision/male_full_height_hands_result_cpu.pbtxt at the
# pinned MediaPipe revision. Without these files the tests skip.
set -euo pipefail

scripts="$(cd "$(dirname "$0")" && pwd)"
destination="${1:-$scripts/../TestAssets}"
url="https://storage.googleapis.com/mediapipe-assets/tasks/testdata/vision/male_full_height_hands.jpg?generation=1782184892683350"
# Same hash as MediaPipe's third_party/external_files.bzl.
expected="8a7fe5be8b90d6078b09913ca28f7e5d342f8d3cde856ab4e3327d2970b887f8"
target="$destination/male_full_height_hands.jpg"

"$scripts/download_holistic_model.sh" "$destination"

curl --fail --location --silent --show-error --output "$target.partial" "$url"
actual="$(shasum -a 256 "$target.partial" | cut -d' ' -f1)"
if [[ "$actual" != "$expected" ]]; then
  rm -f "$target.partial"
  echo "male_full_height_hands.jpg hash changed upstream ($actual); review before updating" >&2
  exit 1
fi
mv "$target.partial" "$target"
echo "Saved $target"
