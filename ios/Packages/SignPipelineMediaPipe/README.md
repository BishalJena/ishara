# SignPipelineMediaPipe

`HolisticLandmarkProvider`: the `LandmarkProvider` from
[SignPipeline](../SignPipeline/README.md) backed by MediaPipe's Holistic Landmarker
(`MediaPipeTasksVision`, video running mode). iOS only; on macOS the target compiles
empty.

It lives in its own package so `SignPipeline` stays dependency-free: SignPipeline,
RecognitionCore and the app's unit tests build on macOS without cloning MediaPipe.
Only the app target links this package.

| | |
|---|---|
| MediaPipe | `https://github.com/google-ai-edge/mediapipe`, pinned to revision `50505c8` (Tasks iOS 1.1.1). The manifest uses `-all_load` unsafe flags, so a version range isn't accepted |
| First resolve | clones about 600 MB and downloads about 98 MB of binaries; later builds use SwiftPM's cache |
| Model | `holistic_landmarker.task` (13.7 MB, Apache-2.0). Fetch it with `Scripts/download_holistic_model.sh <dir>` (hash pinned) and add it to the app bundle. Not committed |
| Platforms | `ios-arm64` and `ios-arm64-simulator` slices only |

```swift
let path = Bundle.main.path(forResource: "holistic_landmarker", ofType: "task")!
let provider = try HolisticLandmarkProvider(modelPath: path)
let landmarks = try provider.landmarks(for: frame)   // off the main thread, increasing timestamps
```

Research notes (model sizes, lite pose model, parity risks) are in the
[SignPipeline README](../SignPipeline/README.md#research-mediapipe-on-ios-checked-23-oct-2026).

## Build

Needs Xcode with an iOS simulator or device destination:

```sh
xcodebuild -scheme SignPipelineMediaPipe -destination 'generic/platform=iOS Simulator' build
```
