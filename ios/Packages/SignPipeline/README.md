# SignPipeline

On-device front half of recognition (PLAN P2): camera or saved video → holistic
landmarks → SignCLIP pose features → Core ML embedding. Matching, the start/stop
detector and calibration live in RecognitionCore, which consumes the plain
values exposed here.

```
CameraFrameSource ─┐                       ┌─▶ FrameSignals (body, wrists) ──▶ detector
                   ├─▶ VideoFrame ─▶ LandmarkProvider ─▶ LandmarkFrame ─┤
VideoFileFrameSource┘   (pixels+time)   (MediaPipe Holistic)            └─▶ ClipBuffer ─▶ FeatureBuilder
                                                                              │ 609 values/frame
                                                                              ▼
                                       SignEmbedding (raw) ◀─ SignEncoder ◀─ EncoderInput [1,256,609]+mask
                                                               (EmbeddingModel / CoreMLEmbeddingModel)
```

| Target | Contents | Platforms |
|---|---|---|
| `SignPipeline` | Landmark types, `FeatureBuilder`, `ClipBuffer`, `EncoderInput`, `SignEncoder`, `CoreMLEmbeddingModel`, frame sources, `LandmarkProvider` | iOS 17, macOS 14 |
| `SignPipelineMediaPipe` | `HolisticLandmarkProvider` (MediaPipe Holistic Landmarker, video mode) | iOS only (compiles empty on macOS) |

## Using it

```swift
let provider = try HolisticLandmarkProvider(modelPath: Bundle.main.path(forResource: "holistic_landmarker", ofType: "task")!)
let encoder = SignEncoder(model: try CoreMLEmbeddingModel(contentsOf: encoderURL))
var clip = ClipBuffer()
for try await frame in VideoFileFrameSource(url: clipURL, pacing: .realTime).frames() {
    let landmarks = try provider.landmarks(for: frame)   // call off the main thread
    let signals = FrameSignals(frame: landmarks)         // → detector
    clip.append(landmarks)                               // while the detector has a clip open
}
let embedding = try encoder.embed(clip)                  // raw; L2-normalize in matching
```

- Get the model with `Scripts/download_holistic_model.sh <dir>` and add it to the app bundle.
- `CameraFrameSource` needs camera permission (`NSCameraUsageDescription`) granted before `frames()`.
- Embeddings are **not** normalized here; clips over 256 frames or under 4 frames are rejected, never truncated.

## Tests

```sh
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer swift test   # macOS host; needs Xcode for XCTest
swift build                                                            # Command Line Tools only
```

The golden fixture comes from the Python reference path; regenerate it only if
the pinned SignCLIP/pose-format versions change (instructions in the script header):

```sh
/tmp/signpipeline-fixture/bin/python Scripts/make_feature_fixture.py
```

The first build clones the MediaPipe repository (~600 MB) and downloads its
binaries (~98 MB); later builds use SwiftPM's cache.

## SignCLIP features: what is ported and why

Reference: `spikes/recognition/signclip.py` `extract` → pose-format 0.9.0
`load_holistic` → SignCLIP `demo_sign.preprocess_pose` at revision `a819944`
([source](https://github.com/J22Melody/fairseq/blob/a819944093876443119f294a2c50c663cecd65b0/examples/MMPT/demo_sign.py)).
`FeatureBuilder` mirrors each step:

| Step | Upstream code | Behaviour |
|---|---|---|
| Assemble | `pose_format.utils.holistic.body_points` / `component_points` | x·width, y·height (pixels); z unchanged. Pose confidence = visibility; detected face/hand point = 1; missing part = zeros, confidence 0 |
| Select | `Pose.get_components` | pose 33, face `FACEMESH_CONTOURS_POINTS` (128, sorted), left hand 21, right hand 21 = 203 points |
| Mask | `NumPyPoseBody.__init__` | point masked where confidence == 0 |
| Normalize | `Pose.normalize(normalization_info(RIGHT_SHOULDER, LEFT_SHOULDER))` | over frames with both shoulders unmasked: centre = mean shoulder midpoint (x, y, z); scale = 1 / mean 3D shoulder distance. **Clip-level**, so features are computed once the clip is closed. Masked points keep raw assembled values |
| Hide legs | `pose_hide_legs` | pose 25–32 set to 0 |
| Flatten | `nan_to_num`, reshape, `.float()` | 203 × (x, y, z) = 609 Float32 |
| Guard | `signclip.py` `pose_fraction == 0` | reject the clip if no frame has both shoulders at visibility ≥ 0.5 |

The masked-point rule is subtle: numpy masked arithmetic leaves masked data
untouched, and `torch.from_numpy` then reads the raw buffer. So a pose landmark
with visibility exactly 0 keeps its pixel coordinates. The fixture covers it.

**Golden test:** `Scripts/make_feature_fixture.py` replaces only MediaPipe's
`Holistic.process` with scripted synthetic results, then runs pose-format's real
`load_holistic` and the checksum-verified upstream `preprocess_pose`
(extracted from the pinned file because `demo_sign.py` imports the whole model at
module level). No video, weights or checkpoint are needed. Swift matches within
1e-5 on all frames of a full-tracking clip and a missing-parts clip.

## Research: MediaPipe on iOS (checked 23 Oct 2026)

Labels: **[doc]** documented by Google, **[obs]** observed by running/inspecting,
**[hyp]** hypothesis to verify.

### Holistic Landmarker is available on iOS

- **[doc]** The [iOS Holistic Landmarker guide](https://developers.google.com/edge/mediapipe/solutions/vision/holistic_landmarker/ios)
  documents `HolisticLandmarker` in `MediaPipeTasksVision`, with image, video and
  live-stream modes. [Overview](https://developers.google.com/edge/mediapipe/solutions/vision/holistic_landmarker):
  33 pose + 478 face + 21 per hand.
- **[obs]** `MediaPipeTasksVision-1.1.1.xcframework` ships `MPPHolisticLandmarker.h`;
  the result has `poseLandmarks`, `faceLandmarks`, `leftHandLandmarks`,
  `rightHandLandmarks` (plus world landmarks), each empty when not detected.
- History: iOS implementation merged in [PR #5153](https://github.com/google-ai-edge/mediapipe/pull/5153)
  (Mar 2024); it was missing from the 0.10.13 build ([#5380](https://github.com/google-ai-edge/mediapipe/issues/5380));
  [v0.10.20](https://github.com/google-ai-edge/mediapipe/releases/tag/v0.10.20) fixed empty pose world
  landmarks on iOS; recent [release notes](https://github.com/google-ai-edge/mediapipe/releases) fix a
  Holistic crash when face detections are missing.

So the PLAN's assumption holds: iOS has the Holistic Landmarker task; the Mac uses legacy
`mp.solutions.holistic` 0.10.21.

### Mapping to the legacy Holistic sets used by `signclip.py`

| Set | Legacy (Mac, complexity 1) | Holistic Landmarker (iOS) | Effect |
|---|---|---|---|
| Pose | 33 BlazePose, full model | 33, same topology and order | **[obs]** the bundled `pose_landmarks_detector.tflite` is 2,818,358 bytes, the size of the *lite* model (lite task: 2,818,390; full: 6,438,874). **[hyp]** iOS pose is lite, so landmarks differ from complexity 1 |
| Face | 468 (no iris refinement) | 478 = same 468 + 10 iris | All 128 contour indices are < 468, so selection is identical; model is Face Mesh V2 vs legacy mesh |
| Hands | left/right 21 each | `leftHandLandmarks` / `rightHandLandmarks` 21 each | Same naming; **[hyp]** same signer-side convention (verify in P3 on a clip with one hand raised) |
| Scores | pose visibility; face/hands none | `visibility`/`presence` are optional numbers | Only pose visibility is used, as pose-format does |

Consequence (PLAN P3 already says this): compare landmarks and embeddings, then
re-embed the enrollment references with the iOS extractor.

**Fallback if Holistic misbehaves** (not implemented): Pose Landmarker (use the
*full* model to match complexity 1) + Face Landmarker + Hand Landmarker
(`numHands = 2`). Map pose and face directly; assign each detected hand to the
nearer pose wrist (15 = left, 16 = right), as legacy Holistic derives hands from
the pose, rather than trusting handedness labels: the iOS hand guide says mirrored
orientations are unsupported, and **[hyp]** the labels follow a camera mirroring
convention. Three separate graphs cost more per frame **[hyp]**.

### Distribution: Swift Package Manager (official), no CocoaPods needed

- **[doc]** [iOS setup guide](https://developers.google.com/edge/mediapipe/solutions/setup_ios): install
  via SPM from `https://github.com/google-ai-edge/mediapipe`, product `MediaPipeTasksVision`; iOS 15+,
  Xcode 14.1+.
- **[obs]** [`Package.swift`](https://github.com/google-ai-edge/mediapipe/blob/50505c8312c7eacb1bd411cecdc4cc9fd08d53cb/Package.swift)
  at `50505c8` (Tasks iOS 1.1.1, 14 Oct 2026) wraps binary xcframeworks from `dl.google.com`:
  TaskGraphs 91.4 MB, Common 4.9 MB, Vision 0.5 MB, Text/Audio/Retrieval/Decision < 0.5 MB each (zip sizes).
  Slices: `ios-arm64` and `ios-arm64-simulator` only (no macOS, no Intel simulator).
- **[obs]** The manifest uses `.unsafeFlags(["-Xlinker", "-all_load"])`, so dependents must pin
  it by branch or revision (this package pins the revision). `MediaPipeTasksCommon` links every task
  binary, so the app carries all of them; size impact not measured.
- **[obs]** CocoaPods `MediaPipeTasksVision` is still published but trails SPM: latest pod 1.0.0
  (28 Jul 2026) vs SPM 1.1.1. No Podfile is proposed.
- The official [holistic sample](https://github.com/google-ai-edge/mediapipe-samples/tree/main/examples/holistic_landmarker/ios)
  also uses the SPM package (branch `master`).

### Models

| File | Size | Notes |
|---|---|---|
| [`holistic_landmarker.task`](https://storage.googleapis.com/mediapipe-models/holistic_landmarker/holistic_landmarker/float16/latest/holistic_landmarker.task) | 13,683,609 B | float16; sha256 `e2dab611…50c3f8`; contains pose detector + landmarks, face detector + landmarks + blendshapes, hand landmarks + ROI refinement |
| `pose_landmarker_full.task` / `_lite` | 9.4 / 5.8 MB | only for the fallback |
| `hand_landmarker.task` | 7.8 MB | only for the fallback |
| `face_landmarker.task` | 3.8 MB | only for the fallback |

Licence: the [BlazePose GHUM 3D](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20BlazePose%20GHUM%203D.pdf),
[Face Mesh V2](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20MediaPipe%20Face%20Mesh%20V2.pdf)
and hand tracking model cards state Apache 2.0. The `latest` URL can change; the
download script pins the hash.

### Running mode and latency

- **[doc]** Modes: `.image`, `.video` (`detect(videoFrame:timestampInMilliseconds:)`, synchronous,
  timestamps must increase), `.liveStream` (`detectAsync` + delegate; results arrive asynchronously).
- Choice: `.video` for both replay and camera. It is deterministic and uses the same code path
  as P3 parity; the camera source drops late frames itself. Live-stream mode can be added if
  latency demands it.
- **[doc]** No iPhone latency is published for the Holistic Landmarker. The only figure is the Hand
  Landmarker on a Pixel 6: 17.12 ms CPU / 12.27 ms GPU
  ([overview](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker)).
  **[hyp]** Holistic runs several models per frame; measure on the iPhone 17 (CPU vs `.GPU`
  delegate) before relying on 30 fps.

### Parity notes for P3

- Pixel scaling uses the **upright** frame size (`VideoFrame.uprightSize`). Check that the Mac
  path's OpenCV width/height match that for portrait clips, or features will differ in aspect.
- Camera frames are unmirrored and rotated to portrait; the reference recordings are unmirrored.
