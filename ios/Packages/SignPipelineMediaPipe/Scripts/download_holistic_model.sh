#!/usr/bin/env bash
# Fetch MediaPipe's Holistic Landmarker model bundle (Apache-2.0, ~13.7 MB) into
# the given directory, checking the hash recorded on 23 Oct 2026. The app
# bundles this file; it is not committed.
set -euo pipefail

destination="${1:?usage: download_holistic_model.sh <destination-directory>}"
url="https://storage.googleapis.com/mediapipe-models/holistic_landmarker/holistic_landmarker/float16/latest/holistic_landmarker.task"
expected="e2dab61191e2dcd0a15f943d8e3ed1dce13c82dfa597b9dd39f562975a50c3f8"
target="$destination/holistic_landmarker.task"

mkdir -p "$destination"
curl --fail --location --silent --show-error --output "$target.partial" "$url"
actual="$(shasum -a 256 "$target.partial" | cut -d' ' -f1)"
if [[ "$actual" != "$expected" ]]; then
  rm -f "$target.partial"
  echo "holistic_landmarker.task hash changed upstream ($actual); review before updating" >&2
  exit 1
fi
mv "$target.partial" "$target"
echo "Saved $target"
