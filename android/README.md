# Ishara for Android

Kotlin + Jetpack Compose app. The shared logic is the same Swift code the iOS app uses
(`ios/Packages/CallSession` and `ios/Packages/RecognitionCore`, unchanged), built for Android
with the Swift SDK for Android into `libIsharaCore.so`. Kotlin calls it through a small
hand-written JNI layer (`android/swift`); commands and results cross as JSON strings.

Right now this is only the foundation: a debug screen and smoke tests that prove the bridge
works. The real screens, the call flow and recognition come later.

## Layout

- `app/`: the Android app (`ai.ishara.demo`). `core/IsharaCore.kt` is the Kotlin side of the bridge.
- `swift/`: Swift package `IsharaAndroidBridge`, product `IsharaCore` (JNI entry points, main-queue pump, event callback).
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

## Build, install, test

```sh
export JAVA_HOME=/opt/homebrew/opt/openjdk@17
cd android
./gradlew :app:assembleDebug                 # also builds libIsharaCore.so (buildSwiftCoreDebug)
./gradlew :app:installDebug                  # needs a device or emulator (arm64 only)
./gradlew :app:connectedDebugAndroidTest     # bridge smoke tests on the device
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
