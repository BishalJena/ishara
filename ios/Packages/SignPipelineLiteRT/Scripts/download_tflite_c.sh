#!/usr/bin/env bash
# Fetch Google's prebuilt TensorFlow Lite (LiteRT) C library for iOS, the binary behind the
# TensorFlowLiteC 2.17.0 CocoaPod (Apache-2.0, ~80 MB download), and keep only
# TensorFlowLiteC.xcframework in ../Frameworks. The tarball hash was recorded on 27 Oct 2026.
# The package cannot load until this has run once; it is not committed.
#
# The pod's frameworks need two fixes for Swift Package Manager, neither of which changes code:
# - each slice ships as one relocatable object; it is repacked as a static archive with
#   libtool (the same object), the form MediaPipe's static frameworks have;
# - Xcode copies static frameworks from packages into the app like MediaPipe's, and refuses one
#   without an Info.plist ("did not contain an Info.plist"), so a minimal one is written.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
frameworks="$here/../Frameworks"
target="$frameworks/TensorFlowLiteC.xcframework"
url="https://dl.google.com/tflite-release/ios/prod/tensorflow/lite/release/ios/release/32/20240729-115310/TensorFlowLiteC/2.17.0/0c10b3543e01f547/TensorFlowLiteC-2.17.0.tar.gz"
expected="9667b476015f136e5b332ce040e12822c4ac6d5c58947882ddc809cdff0fb99e"

if [[ ! -f "$target/Info.plist" ]]; then
  work="$(mktemp -d)"
  trap 'rm -rf "$work"' EXIT
  curl --fail --location --silent --show-error --output "$work/tflite.tar.gz" "$url"
  actual="$(shasum -a 256 "$work/tflite.tar.gz" | cut -d' ' -f1)"
  if [[ "$actual" != "$expected" ]]; then
    echo "TensorFlowLiteC tarball hash changed upstream ($actual); review before updating" >&2
    exit 1
  fi
  tar -xzf "$work/tflite.tar.gz" -C "$work" "TensorFlowLiteC-2.17.0/Frameworks/TensorFlowLiteC.xcframework"
  mkdir -p "$frameworks"
  mv "$work/TensorFlowLiteC-2.17.0/Frameworks/TensorFlowLiteC.xcframework" "$target"
  echo "Saved $target"
fi

for framework in "$target"/*/TensorFlowLiteC.framework; do
  binary="$framework/TensorFlowLiteC"
  if ! file "$binary" | grep -q "ar archive"; then
    mv "$binary" "$binary.o"
    libtool -static -o "$binary" "$binary.o"
    rm "$binary.o"
    echo "Repacked as a static archive: ${framework#"$target/"}"
  fi
  if [[ ! -f "$framework/Info.plist" ]]; then
    platform=iPhoneOS
    [[ $framework == *simulator* ]] && platform=iPhoneSimulator
    cat >"$framework/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key><string>TensorFlowLiteC</string>
  <key>CFBundleIdentifier</key><string>org.tensorflow.lite.TensorFlowLiteC</string>
  <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
  <key>CFBundleName</key><string>TensorFlowLiteC</string>
  <key>CFBundlePackageType</key><string>FMWK</string>
  <key>CFBundleShortVersionString</key><string>2.17.0</string>
  <key>CFBundleVersion</key><string>2.17.0</string>
  <key>CFBundleSupportedPlatforms</key><array><string>$platform</string></array>
  <key>MinimumOSVersion</key><string>12.0</string>
</dict>
</plist>
PLIST
    echo "Wrote Info.plist: ${framework#"$target/"}"
  fi
done
