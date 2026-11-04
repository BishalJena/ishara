# Ishara for Android

The Android version of the Ishara app: the same two flows as the iPhone app (Ishara runs the
call and you step in, or the classic flow where you sign every reply), the same safety rules
and the same backend. Nothing is spoken unless you tap Send. Calls placed through the backend
come from Ishara's calling number, which Bolna provides, not your own number.

## How it's built

- **Shared Swift core.** `ios/Packages/CallSession` (the turn rules, backend client, live call)
  and `ios/Packages/RecognitionCore` (sign detector, open-set rule) are compiled unchanged for
  Android with the Swift SDK for Android into `libIsharaCore.so`. Kotlin calls it through a small
  hand-written JNI layer (`android/swift`); commands and results cross as JSON strings.
- **Kotlin ports.** The iOS *app target* (screens, view models, call drivers, history, settings,
  launch options) is ported to Kotlin + Jetpack Compose. The rule: Swift *packages* are shared,
  the app target is ported. The SwiftUI views stay the spec for layout, strings and colours.
- **Recognition on the phone.** CameraX frames → MediaPipe Holistic landmarks → RecognitionCore's
  detector → the public Kaggle ASL model on LiteRT → RecognitionCore's open-set rule → word chips
  ([Recognition](#recognition)).
- API keys stay on the backend; the app holds only the backend URL and its app token.

## Layout

- `app/`: the Android app (`ai.ishara.demo`).
  - `core/IsharaCore.kt`: the JNI functions; `core/CoreEvents.kt`: routes Swift events by their `type`.
  - `core/call/`: the call layer over CallSession. `CallCore` starts live calls and local sessions;
    a session is a `CallStore` (snapshot `StateFlow` plus `TurnStore` actions).
  - `call/`, `models/`, `app/`: ports of the iOS app target. `call/FakeCallDriver` plays the demo
    call into a local session's real `TurnStore`; `call/ActiveCallViewModel` maps its snapshot onto
    the call screens; `app/AppNavigator` is iOS `AppRootView`'s routing and `app/AppRoot` shows the routes.
  - `recognition/`: the recognizer contract the screens use; `recognition/core` (RecognitionCore over
    JNI), `recognition/landmarks` and `recognition/pipeline` (the real camera / clip pipeline).
  - `ui/components/`: shared, stateless Compose pieces tagged with the iOS accessibility identifiers;
    `ScreenParts.kt` holds the iOS-look building blocks (bottom bar, grouped Form sections, bordered
    buttons) and maps Dynamic Type onto the font scale (≥ 1.6 counts as an accessibility size,
    > 1.2 as larger than XL). Text styles are iOS's (`ui/theme/IsharaType.kt`).
  - `ui/home/`, `ui/classic/`, `ui/steer/`, `ui/notes/`: one file per screen, plus the screen models
    (`BriefModel`, `NotesModel`, `SteerLogic`).
- `swift/`: Swift package `IsharaAndroidBridge`, product `IsharaCore` (JNI entry points, main-queue pump,
  event callback, `Call/`: the session registry, snapshots and commands, and `Recognition/`).
- Nothing from `ios/` is copied: Gradle packages `ios/Ishara/Resources/asl-bundle.json` as the asset
  `asl-bundle.json`, and the models and sample clips straight from `ios/Ishara/LocalAssets`.

## Setup from zero (macOS)

Linux works the same way with the Linux downloads; CI does it on Ubuntu (`.github/workflows/ci.yml`).

1. **Android tools and JDK 17:**

   ```sh
   brew install --cask android-commandlinetools
   brew install openjdk@17
   export JAVA_HOME=/opt/homebrew/opt/openjdk@17
   export ANDROID_HOME=/opt/homebrew/share/android-commandlinetools
   sdkmanager "platforms;android-36" "build-tools;36.1.0" "platform-tools" "ndk;30.0.16248370"
   ```

2. **Swift 6.4.2 and the Swift SDK for Android.** Xcode's `/usr/bin/swift` can't build for
   Android: it needs the open-source toolchain, and the toolchain and SDK versions must match exactly.

   ```sh
   brew install swiftly && swiftly init
   swiftly install 6.4.2 && swiftly use 6.4.2
   swift sdk install https://download.swift.org/swift-6.4.2-release/android-sdk/swift-6.4.2-RELEASE/swift-6.4.2-RELEASE_android.artifactbundle.tar.gz \
     --checksum 4d6ad63ea74becd58e123ff58b1b48c3be5ec0db0dff0ea5abe37ac007dd3233
   swift sdk list                     # swift-6.4.2-RELEASE_android
   ```

3. **Link the SDK to the NDK** (once, and again after moving the NDK):

   ```sh
   ANDROID_NDK_HOME=$ANDROID_HOME/ndk/30.0.16248370 \
     ~/Library/org.swift.swiftpm/swift-sdks/swift-6.4.2-RELEASE_android.artifactbundle/swift-android/scripts/setup-android-sdk.sh
   ```

   On Linux the bundle is under `~/.swiftpm/swift-sdks/` instead.

4. **An emulator** (arm64 only; the app ships only `arm64-v8a`):

   ```sh
   sdkmanager "emulator" "system-images;android-36;google_apis;arm64-v8a"
   avdmanager create avd -n ishara -k "system-images;android-36;google_apis;arm64-v8a" -d pixel_8
   $ANDROID_HOME/emulator/emulator -avd ishara &
   ```

   Or a phone with USB debugging on.

5. **`android/local.properties`** (never committed):

   ```properties
   sdk.dir=/opt/homebrew/share/android-commandlinetools
   # Optional backend for live calls; they become BuildConfig fields:
   ishara.backendUrl=http://10.0.2.2:8000
   ishara.appToken=<APP_TOKEN>
   # Optional toolchain overrides (the defaults are shown):
   # swift.bin=/Users/<you>/.swiftly/bin/swift   (else `swift` on the PATH)
   # swift.sdk=swift-6.4.2-RELEASE_android
   # android.ndk=<sdk.dir>/ndk/30.0.16248370
   ```

   The toolchain settings can also come from `SWIFT_BIN`, `SWIFT_SDK` and `ANDROID_NDK_HOME`
   (`local.properties` wins), and `sdk.dir` from `ANDROID_HOME`. Without the backend settings the
   app can't place a live call and uses the fake call instead; Home says why, like iOS.

6. **Models and sample clips** (optional; not in Git). They live once, in the iOS app's
   `ios/Ishara/LocalAssets` ([what each file is](../ios/Ishara/LocalAssets/README.md)), and the
   build packages whichever exist:

   ```sh
   ios/Packages/SignPipelineMediaPipe/Scripts/download_holistic_model.sh ios/Ishara/LocalAssets
   ios/Packages/SignPipelineLiteRT/Scripts/download_asl_model.sh ios/Ishara/LocalAssets
   ```

   Debug builds also package `ios/Ishara/LocalAssets/SampleSigns/*.mp4|mov|m4v` for the emulator,
   which has no usable camera (local evaluation only; never commit third-party clips). Without the
   models the app still builds and runs: Get ready says why recognition can't start, or every sign
   shows `[?]`.

## Build, install, run

```sh
cd android
./gradlew :app:assembleDebug        # also builds libIsharaCore.so (buildSwiftCoreDebug)
./gradlew :app:installDebug         # to the running emulator or phone
adb shell am start -n ai.ishara.demo/.MainActivity --es IsharaDriver fake --es IsharaFlow classic
```

(`adb` is `$ANDROID_HOME/platform-tools/adb`.) `buildSwiftCoreDebug` / `buildSwiftCoreRelease` run
`swift build` in `android/swift` and copy `libIsharaCore.so` plus every library it needs (Swift
runtime, Foundation, `libc++_shared.so`) into the APK.

**Launch options** are `--es` extras with the iOS launch argument names (`app/DemoLaunchOptions.kt`):
`IsharaDriver fake|live` (live by default; without backend settings the fake call stands in and
Home says why), `IsharaFlow steer|classic`, `IsharaRecognition scripted|pipeline`,
`IsharaReplay "hello,?,tomorrow?,frame"`, `IsharaFakeNotDelivered`, `IsharaFakeInterrupt`,
`IsharaFakeConnectionDrop reconnects|staysDown`, `IsharaFakeOpenQuestion tap|<time word>`,
`IsharaFakeOpenQuestionText`, `IsharaFakeBolnaSummary <s>`, `IsharaFakeTimeScale <x>`,
`IsharaFixture <state>` (debug), `IsharaCallHistory memory|<dir>`, `IsharaSampleSigns <dir>` and
`IsharaUITestName <name>` (iOS `ISHARA_UITEST_NAME`). Booleans may be `--ez` or `--es ... YES`.

### Against a local backend

The backend's development server simulates Bolna and the receptionist, so nothing is dialled
and no paid API is used ([backend/README.md](../backend/README.md#local-development-server-no-bolna-no-cost)):

```sh
cd backend && uv run python -m scripts.local_demo     # http://127.0.0.1:8000, token ishara-local-demo
```

- **Emulator:** `ishara.backendUrl=http://10.0.2.2:8000` (the emulator's address for this Mac).
- **USB phone:** `adb reverse tcp:8000 tcp:8000` and `ishara.backendUrl=http://localhost:8000`.
- `ishara.appToken=ishara-local-demo`, then rebuild and launch with `--es IsharaDriver live`.
- Debug builds allow cleartext http/ws only to `10.0.2.2`, `127.0.0.1` and `localhost`
  (`src/debug/res/xml/network_security_config.xml`); release builds need https.

## Tests

```sh
cd android
./gradlew :app:testDebugUnitTest :app:lintDebug :app:assembleDebug   # JVM tests, lint, build
ANDROID_SERIAL=emulator-5554 ./gradlew :app:connectedDebugAndroidTest   # on the emulator
```

- **JVM tests** (`src/test`): drivers, config, wire format, screen models and recognition logic with
  scripted RecognitionCore rules (the Swift library only runs on Android).
- **Device tests** (`src/androidTest`): the JNI bridge, the call layer against an in-process fake
  backend (mockwebserver), the UI flows that mirror `ios/IsharaUITests`, and recognition (see
  [Recognition](#recognition)); tests that need missing models or clips skip.
- `scripts/verify.sh` runs the JVM tests, lint and build, builds `CallSession` and
  `RecognitionCore` for Android on their own (so an Apple-only change shows up), and runs the
  device tests on `ANDROID_SERIAL` or a running emulator; a plugged-in phone is never picked by
  itself. Missing tools show as `SKIPPED`.
- CI's `android` job does the same except the device tests, when `android/**` or the shared
  packages change.

## Differences from iOS

- **Icons:** SF Symbols become Material icons (`material-icons-extended`).
- **Ongoing-call notification** instead of the Live Activity. On the lock screen it shows only
  that a call is on, the timer and End call ("Unlock to step in"), not what was said.
- **Foreground service:** while a steer call is on, a `specialUse` foreground service keeps the call
  running when you leave the app. Google Play needs it declared in the Play Console with a
  justification (the manifest's `PROPERTY_SPECIAL_USE_FGS_SUBTYPE` text) before release.
- **Portrait only** (`android:screenOrientation="portrait"`).
- **Attachments:** a PDF's text layer on Android 15+, otherwise on-device OCR of its first
  10 pages; photos by OCR (ML Kit).
- **Camera in a steer call** starts (and permission is asked) only when you tap Sign, not when the
  call starts. Android asks for permissions only from an Activity, so the screens ask.
- No contacts permission: the picker hands back just the picked number.
- Only `arm64-v8a`, so no x86_64 emulators. The SignCLIP / Core ML fallback recognizer isn't ported.

## Things to know

- **Main-queue pump:** Android never drains `DispatchQueue.main`, so `@MainActor` Swift code
  would never run. `IsharaApplication.onCreate` calls `IsharaCore.installMainQueuePump()`,
  which lets the Android main looper drain it. libdispatch ties its main queue to the thread
  that loads the library, so load `IsharaCore` first on the main thread, never from a worker thread.
- The Swift runtime is linked dynamically (`--static-swift-stdlib` failed to link with 6.4.2), so
  the APK carries about 70 MB of `.so` files; ICU alone is 40 MB.
- AndroidX libraries newer than core 1.18 / Compose BOM 2026.06 need compileSdk 37; the app stays on 36.
- The classic screens are ports of the SwiftUI views, which stay the spec (layout order, strings,
  colours). SF Symbols become Material icons from `material-icons-extended` (the BOM's 1.7.8). UI tests
  for the classic and Call for me flows live in `androidTest/.../ui/classic` (they mirror
  `ios/IsharaUITests`); `CallLayoutUiTest` sets the system font scale to 2.0 and restores it.
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
  and each should be collected once. A local session's `sink`, when set, takes the store's messages
  instead, inside the action that sent them, like iOS's `OutgoingMessageSink`: the fake call needs that
  so its goodbye caption lands before `end()` closes the store.
- The call socket runs on OkHttp (`core/call/OkHttpWebSockets.kt`), driven by Swift's
  `KotlinWebSocketTransport` over JNI; REST stays on Swift's URLSession. Swift's own Android
  WebSocket turns unknown close codes into 1003, which would hide the backend's 4401 / 4404 / 4409.
- Debug builds allow cleartext http/ws to `10.0.2.2`, `127.0.0.1` and `localhost` only
  (`src/debug/res/xml/network_security_config.xml`). OkHttp enforces Android's network security
  policy and Swift's URLSession doesn't, so a backend at a LAN address needs adding there.

## Steer screens

Ports of iOS `SetupView`, `SteerCallView`, `SteerGistView`, `SettingsSheet`, `RecentCallView` and
`RecentCallsSection`, drawn in the iOS system colours (`ui/steer/SteerStyle.kt`, light and dark).

- **Contacts:** the picker lists phone numbers (`ACTION_PICK` on `Phone.CONTENT_TYPE`) and hands
  back only the picked row with a temporary read grant, so the app asks for no contacts permission.
- **Attachments:** photos (system photo picker) and PDFs or images (document picker) are read on the
  phone (`ui/steer/AttachmentReader.kt`): a PDF's text layer on Android 15+, otherwise on-device OCR
  (ML Kit text recognition, bundled Latin model) of its first 10 pages; photos by OCR. Text is
  trimmed and capped at 20,000 characters, like iOS.
- **Ongoing-call notification** (the iOS Live Activity, `call/notification/`): the contact, who is
  answering, a running timer, the latest line and **End call**, which ends the call through the app
  exactly like the End button. While a steer call is on, a foreground service of type `specialUse`
  keeps the process (and so the call's socket) running when the user leaves the app; it stops with
  the call or the app's task. A call that ends while the app is away leaves "Call ended · open
  Ishara for the gist" for a minute. Notifications are asked for on the first Call (Android 13+);
  without them the call and the service run as usual, only nothing is shown.
