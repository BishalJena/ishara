# Ishara iOS app

SwiftUI demo app (iOS 17+, iPhone, portrait) with the four workflow screens. It runs in
two call modes and two recognition modes:

| | Fake (default) | Live |
|---|---|---|
| **Call** (`-IsharaDriver`) | `FakeCallDriver` plays the PLAN §1 clinic call on timers. Nothing is dialled | `LiveCallDriver` → Ishara backend (`POST /calls` + call WebSocket) → Bolna dials (Path B). **Places a real, paid call** |
| **Recognition** (`-IsharaRecognition`) | `scripted`: replays fixed results (the fake call's script, `-IsharaReplay`, or the replay menu) | `pipeline`: MediaPipe Holistic → start/stop detector → SignCLIP (Core ML) → matcher. Camera on a device, saved videos in the simulator |

Recognition defaults to `scripted` with the fake call and to `pipeline` with the live one.

```
Views ─▶ ActiveCallViewModel ─▶ TurnStore (CallSession: every SEND safety rule)
              │                     ▲ messages        │ AppMessage
              │                     │                 ▼
              │               CallDriver: FakeCallDriver │ LiveCallDriver → LiveCall → backend
              ▼
     RecognitionController: Scripted │ Pipeline (frames → landmarks → detector → encoder → matcher)
```

The SEND rules live in one place, `TurnStore` in [CallSession](Packages/CallSession/README.md):
single-use SEND tied to a turn id, stale drafts ignored, `?` never sent, re-SEND only on
an explicit tap with a new turn id, everything wiped on End or a lost connection.

## Open

```sh
open ios/Ishara.xcodeproj
```

Pick the **Ishara** scheme and an iPhone simulator, then Run. The first open resolves
the local packages and clones MediaPipe (about 600 MB, once). To run on a device,
choose your own team under Signing & Capabilities. Don't commit it:
`DEVELOPMENT_TEAM` stays empty in Git.

## Configure the backend (live call only)

The backend URL and the demo `APP_TOKEN` come from an untracked xcconfig, never from Git:

```sh
cp ios/Ishara/Config/Secrets.example.xcconfig ios/Ishara/Config/Secrets.xcconfig
# edit Secrets.xcconfig: ISHARA_BACKEND_URL and ISHARA_APP_TOKEN
```

- `//` starts a comment in xcconfig files, so write URLs as `https:/$()/your-app.herokuapp.com`.
  A backend on this Mac works from the simulator as `http:/$()/127.0.0.1:8000`.
- The values reach the app as the `IsharaBackendURL` / `IsharaAppToken` Info.plist keys.
  With `-IsharaDriver live` and a missing or broken value, Home says what's wrong and CALL stays off.
- The app sends only a contact id (`clinic` for City Clinic, `mehta-office`); the numbers live in
  the backend's `ALLOWED_RECIPIENTS` (e.g. `clinic=+91…`). Home keeps the note that Path B calls
  come from a Bolna number, not your own.
- A live call costs money (Bolna about ₹5.5/min plus telephony) and must only go to a
  consenting teammate on the allowlist.

## Recognition files (pipeline only)

Models and recordings go in `ios/Ishara/LocalAssets/` (gitignored, copied into the app as a
folder). See [LocalAssets/README.md](Ishara/LocalAssets/README.md): `holistic_landmarker.task`,
`SignCLIPEncoder.mlmodelc` / `.mlpackage`, `recognition-bundle.json`, and `SampleSigns/*.mov`
for the simulator (including `rest.mov` for calibration).

- No recognition bundle or encoder: every accepted sign shows **[?]**. The app never guesses.
- Rejected attempts (too short, too long, lost tracking) produce no chip at all.
- The Core ML encoder always runs on CPU+GPU; the FP16 package is wrong on the Neural Engine.
- In the simulator, a **Replay a sign** menu on the camera area plays a saved clip (pipeline)
  or injects a result (scripted + live call), since there is no camera.

## Run

| What | Launch arguments |
|---|---|
| Demo without a backend (default) | none |
| Fake call, real recognition on saved videos | `-IsharaRecognition pipeline` |
| Live call, real recognition | `-IsharaDriver live` |
| Live call, results injected from the replay menu | `-IsharaDriver live -IsharaRecognition scripted` |
| UI test with fixed results | `-IsharaReplay hello,doctor,?` (signs, or `?` for unsure, played ~2 s apart once the call screen opens) |

Other switches:

| Argument | Effect |
|---|---|
| `-IsharaFakeNotDelivered YES` | The first SEND of turn 2 comes back "not delivered", so you have to tap SEND again |
| `-IsharaFakeTimeScale 0.5` | Runs the Get ready checks and the fake call twice as fast |
| `-IsharaFixture <name>` | Debug builds only. Opens a prepared state: `home`, `getReady`, `signing`, `speaking`, `delivered`, `notDelivered`, `ended`, `connectionLost` |

Set them in the scheme (Run → Arguments) or pass them to `xcrun simctl launch`:

```sh
xcrun simctl launch booted ai.ishara.demo -IsharaFixture signing
xcrun simctl io booted screenshot /tmp/ishara-signing.png
```

## Regenerate the project

`ios/project.yml` is the source of truth. Edit it, then:

```sh
brew install xcodegen   # once
xcodegen generate --spec ios/project.yml
```

Commit `project.yml` and `Ishara.xcodeproj` together.

## Build and test

App (needs Xcode and an iPhone simulator):

```sh
xcrun simctl list devices available | grep iPhone   # pick a simulator name
xcodebuild -project ios/Ishara.xcodeproj -scheme Ishara \
  -destination 'platform=iOS Simulator,name=iPhone 17' test
```

This runs the unit tests (`IsharaTests`) and the UI tests (`IsharaUITests`),
which walk the whole PLAN §1 call on the fake driver at `-IsharaFakeTimeScale 0.5`
(about a minute). Add `-only-testing:IsharaTests` for just the unit tests.

Packages (macOS host, no simulator needed):

```sh
for p in CallSession RecognitionCore SignPipeline; do (cd ios/Packages/$p && swift test); done
```

`SignPipelineMediaPipe` only builds for iOS (see its README). If `xcode-select` points at
the Command Line Tools, prefix the commands with
`DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer`.

App tests cover the view model over a real `TurnStore`, the live driver against an
in-memory backend (HTTP + WebSocket), reconnects, the config loader, the fake call end to
end, and recognition with a stub landmark provider and encoder (accepted sign → chip,
low confidence → [?], no bundle → [?], rejected attempt → nothing).

## Layout

| Path | What |
|---|---|
| `Ishara/Models` | Call setup, camera pill state, draft badges |
| `Ishara/Call` | `CallDriver`, `ActiveCallViewModel`, `LiveCallDriver`, `FakeCallDriver` and the demo script |
| `Ishara/Recognition` | `RecognitionController`, the scripted and pipeline implementations, `RecognitionSession` (checklist, calibration, detector), `SegmentClassifier`, frame feeds, assets |
| `Ishara/Views` | Home, Get ready, Active call and shared components |
| `Ishara/App` | App entry, navigation, `AppServices` (picks driver and recognizer), config, launch options and Debug fixtures |
| `Ishara/Config` | `Ishara.xcconfig`, `Secrets.example.xcconfig` (copy to the gitignored `Secrets.xcconfig`) |
| `Ishara/LocalAssets` | Untracked models and recordings |
| `IsharaTests` | XCTest for the app |
| `IsharaUITests` | XCUITest that clicks through the §1 demo call, plus the not-delivered retry |
| `Packages/CallSession` | Wire messages, backend client, `TurnStore`, `LiveCall` |
| `Packages/RecognitionCore` | Start/stop detector, calibration, recognition bundle, matcher |
| `Packages/SignPipeline` | Frame sources, landmarks, SignCLIP features, Core ML encoder |
| `Packages/SignPipelineMediaPipe` | MediaPipe Holistic landmark provider (iOS only) |

## Still needs a device or Xcode

- P3 parity: the same saved videos through the simulator pipeline and the Mac; re-embed the
  enrollment references with the iOS extractor before trusting the bundle.
- T1: install on the iPhone, grant camera permission, measure Holistic + encoder latency.
- The `SignPipelineMediaPipe` adapter has not yet been compiled against the real MediaPipe module.
