# Ishara for Android

Kotlin + Jetpack Compose app. The shared logic is the same Swift code the iOS app uses
(`ios/Packages/CallSession` and `ios/Packages/RecognitionCore`, unchanged), built for Android
with the Swift SDK for Android into `libIsharaCore.so`. Kotlin calls it through a small
hand-written JNI layer (`android/swift`); commands and results cross as JSON strings.

So far: the bridge, the call layer (CallSession's `TurnStore`, `BackendClient` and `LiveCall`
behind a Kotlin facade, plus the ported live call driver), on-device recognition (see
[Recognition](#recognition)) and a debug screen. The real screens and the fake demo call come later.

## Layout

- `app/`: the Android app (`ai.ishara.demo`).
  - `core/IsharaCore.kt`: the JNI functions; `core/CoreEvents.kt`: routes Swift events by their `type`.
  - `core/call/`: the call layer over CallSession. `CallCore` starts live calls and local sessions;
    a session is a `CallStore` (snapshot `StateFlow` plus `TurnStore` actions).
  - `call/`, `models/`, `app/`: ports of the iOS app target's `CallDriver`, `LiveCallDriver`, `CallSetup`
    and `AppConfig` (the rule: Swift *packages* are shared, the iOS *app target* is ported to Kotlin).
  - `recognition/`: the recognizer contract the screens use; `recognition/core` (RecognitionCore over
    JNI), `recognition/landmarks` and `recognition/pipeline` (the real camera / clip pipeline).
- `swift/`: Swift package `IsharaAndroidBridge`, product `IsharaCore` (JNI entry points, main-queue pump,
  event callback, `Call/`: the session registry, snapshots and commands, and `Recognition/`).
- The recognition bundle is not copied into the repo: Gradle packages
  `ios/Ishara/Resources/asl-bundle.json` as the asset `asl-bundle.json`.

## One-time setup (macOS)

1. Android tools: `brew install --cask android-commandlinetools` and `brew install openjdk@17`, then
   `sdkmanager "platforms;android-36" "build-tools;36.1.0" "platform-tools" "ndk;30.0.16248370"`
   (add `"emulator" "system-images;android-36;google_apis;arm64-v8a"` for an emulator).
2. Swift: `brew install swiftly`, then `swiftly install 6.4.2` and
   `swift sdk install` the matching `swift-6.4.2-RELEASE_android` SDK (see swift.org's
   "Getting started with the Swift SDK for Android"). Run the SDK's `scripts/setup-android-sdk.sh` once.
   Xcode's `/usr/bin/swift` can't build for Android: the toolchain and SDK versions must match exactly.
3. `android/local.properties` (not committed):

   ```properties
   sdk.dir=/opt/homebrew/share/android-commandlinetools
   # Optional; these are the defaults:
   # swift.bin=/Users/<you>/.swiftly/bin/swift
   # swift.sdk=swift-6.4.2-RELEASE_android
   # android.ndk=/opt/homebrew/share/android-commandlinetools/ndk/30.0.16248370
   ```

   The same settings can come from `SWIFT_BIN`, `SWIFT_SDK` and `ANDROID_NDK_HOME`.

4. Optional, for live calls: add the backend to `android/local.properties` (it becomes BuildConfig
   fields; never commit it):

   ```properties
   ishara.backendUrl=http://10.0.2.2:8000   # the emulator's address for a backend on this Mac
   ishara.appToken=<APP_TOKEN>
   ```

   Without them `AppConfig.fromBuildConfig()` fails and the app must use the fake call, like iOS.

## Build, install, test

```sh
export JAVA_HOME=/opt/homebrew/opt/openjdk@17
cd android
./gradlew :app:assembleDebug                 # also builds libIsharaCore.so (buildSwiftCoreDebug)
./gradlew :app:installDebug                  # needs a device or emulator (arm64 only)
./gradlew :app:testDebugUnitTest             # JVM tests (driver, config, wire format)
./gradlew :app:connectedDebugAndroidTest     # bridge and call tests on the device (fake backend in-process)
adb shell am start -n ai.ishara.demo/.MainActivity
```

`buildSwiftCoreDebug` / `buildSwiftCoreRelease` run `swift build` in `android/swift` and copy
`libIsharaCore.so` plus every library it needs (Swift runtime, Foundation, `libc++_shared.so`)
into the APK. Only arm64-v8a is built.

## Things to know

- **Main-queue pump:** Android never drains `DispatchQueue.main`, so `@MainActor` Swift code
  would never run. `IsharaApplication.onCreate` calls `IsharaCore.installMainQueuePump()`,
  which lets the Android main looper drain it. libdispatch ties its main queue to the thread
  that loads the library, so load `IsharaCore` first on the main thread, never from a worker thread.
- The Swift runtime is linked dynamically (`--static-swift-stdlib` failed to link with 6.4.2), so
  the APK carries about 70 MB of `.so` files; ICU alone is 40 MB.
- AndroidX libraries newer than core 1.18 / Compose BOM 2026.06 need compileSdk 37; the app stays on 36.
  OkHttp 5.5 needs 37 too, so OkHttp and mockwebserver3 stay on 5.4.

## Recognition

Decision D8 as on iOS: the public Kaggle ASL Signs 1st-place model, full 250-way softmax, and
RecognitionCore's open-set rule (chip only for a bundle word at margin ≥ 0.3 and p ≥ its cut-off,
grey zone → "Did you mean …?", otherwise `?`). Recognition only makes chips; nothing is spoken
until the user taps SEND.

- **Shared over JNI** (`recognition/core`, `swift/Sources/IsharaCore/Recognition`): RecognitionCore's
  `SignDetector` (a `Long` handle, one call per frame), rest calibration, `FramingGuard`,
  `ClipQuality` and `LogitsMatcher` (logits cross as a `FloatArray`). Kotlin sees them as
  `RecognitionRules` and `LogitsMatching`.
- **Ported to Kotlin** (`recognition/landmarks`, `recognition/pipeline`): SignPipeline's
  `LandmarkFrame` / `FrameSignals` / `KaggleLayout`, the app target's `RecognitionSession`,
  `SegmentClassifier` (ASL engine only; the SignCLIP / Core ML path is not ported),
  `PipelineRecognitionController`, `ClipFeed` and `CameraFeed`, and the Apple-only packages as
  `HolisticLandmarkProvider` (MediaPipe Tasks Vision, video mode, CPU, confidences 0.5) and
  `LiteRTLogitsModel` (LiteRT, XNNPACK, 2 threads, input resized per clip).
- `RecognitionPipelines.camera(context, scope)` and `.clips(context, scope)` build the real
  controller. Frames: CameraX front camera (`ImageAnalysis` 16:9 ≈ 1280×720, latest frames only,
  turned upright, unmirrored) or saved clips (MediaExtractor times + MediaMetadataRetriever frames,
  real time, `rest` first, 0.8 s hold after each clip) → Holistic landmarks → session (checklist,
  2 s calibration, detector) → accepted segment → Kaggle layout → LiteRT → matcher → chip.
  The preview is CameraX's mirrored `PreviewView`; `PreviewMapping` maps overlay points onto it.
- Camera permission: Android asks only from an Activity, so the screens request `CAMERA` and call
  `LiveCamera.onPermissionResult(granted)`; frames start once it is granted.

**Assets** (not in Git, the iOS app's single source): run
`ios/Packages/SignPipelineMediaPipe/Scripts/download_holistic_model.sh ios/Ishara/LocalAssets` and
`ios/Packages/SignPipelineLiteRT/Scripts/download_asl_model.sh ios/Ishara/LocalAssets`; the build
packages whichever exist. Without the Holistic model the controller's `failure` says why; without
the ASL model or with an invalid bundle the `notice` says every sign will show `[?]`. Debug builds
also package `ios/Ishara/LocalAssets/SampleSigns/*.mp4` (made as in that folder's README; local
evaluation only) for the emulator, which has no usable camera.

**Tests:** JVM tests use scripted RecognitionCore rules (the Swift library only runs on the
device) and SignPipeline's landmark fixture. Device tests run every RecognitionCore detector
fixture through JNI, the iOS session / classifier / controller tests against the real detector and
bundle, LiteRT against the Mac runtime's logits (`runtime_parity.json`), MediaPipe against its
reference photo (run `download_holistic_test_assets.sh` first) and, when `SampleSigns` holds a
`rest` clip, the whole pipeline on the saved clips (`ClipReplayEndToEndTest`). Missing models or
clips skip those tests.

## Call layer bridge

- Each call session in Swift wraps one `TurnStore`. **Live** sessions come from `CallCore.startCall`
  (`POST /calls` and the socket, all in Swift). **Local** sessions (`CallCore.startLocalSession`) have no
  socket: Kotlin feeds backend messages with `receive` and reads what the store sends from `outgoing`.
  The fake demo call and tests use them, so every path runs the same Swift safety rules.
- After every change Swift sends a full snapshot (`{"type":"state",...}`), at most one per main-queue
  turn, so a snapshot lands just after the action that caused it, not inside it.
- Session actions must run on the main thread (they throw `IllegalStateException` otherwise). Async
  work (start call, brief, notes, reconnect, last close) answers with a `result` event for its request id.
- `outgoing` and `connectionLost` are buffered channels: nothing is lost before they are collected,
  and each should be collected once.
- The call socket runs on OkHttp (`core/call/OkHttpWebSockets.kt`), driven by Swift's
  `KotlinWebSocketTransport` over JNI; REST stays on Swift's URLSession. Swift's own Android
  WebSocket turns unknown close codes into 1003, which would hide the backend's 4401 / 4404 / 4409.
- Debug builds allow cleartext http/ws to `10.0.2.2`, `127.0.0.1` and `localhost` only
  (`src/debug/res/xml/network_security_config.xml`). OkHttp enforces Android's network security
  policy and Swift's URLSession doesn't, so a backend at a LAN address needs adding there.
