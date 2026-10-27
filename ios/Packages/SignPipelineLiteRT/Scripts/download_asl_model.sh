#!/usr/bin/env bash
# Fetch the public ASL Signs 1st-place model (decision D8; code MIT, training corpus CC-BY 4.0)
# into the given directory as asl-signs.tflite, checking the hash the recognition bundle records.
# The app bundles this file from ios/Ishara/LocalAssets; it is not committed.
set -euo pipefail

destination="${1:?usage: download_asl_model.sh <destination-directory>}"
url="https://huggingface.co/sign/kaggle-asl-signs-1st-place/resolve/main/model.tflite"
expected="f55a2bb1ebe6d1e912a98e31c6ef3f995c9ae261f408fe115f2008099d3f0bb7"
target="$destination/asl-signs.tflite"

mkdir -p "$destination"
curl --fail --location --silent --show-error --output "$target.partial" "$url"
actual="$(shasum -a 256 "$target.partial" | cut -d' ' -f1)"
if [[ "$actual" != "$expected" ]]; then
  rm -f "$target.partial"
  echo "model.tflite hash changed upstream ($actual); review before updating" >&2
  exit 1
fi
mv "$target.partial" "$target"
echo "Saved $target"
