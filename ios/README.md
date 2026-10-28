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
an explicit tap with a new turn id, and chips, drafts and pending approvals wiped on End or a
lost connection. The captions stay on screen as a read-only transcript of the call.

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
  the backend's `ALLOWED_RECIPIENTS` (e.g. `clinic=+91…`). Home and Get ready both say, in plain
  words, that calls come from Ishara's calling number (Bolna's, Path B), not your own, and
  that the receptionist hears an automated voice.
- A live call costs money (Bolna about ₹5.5/min plus telephony) and must only go to a
  consenting teammate on the allowlist.

## Recognition files (pipeline only)

Before the first build, fetch the LiteRT library the `SignPipelineLiteRT` package links (the
package cannot load without it; checksum-verified, not committed):

```sh
Packages/SignPipelineLiteRT/Scripts/download_tflite_c.sh
```

Models and recordings go in `ios/Ishara/LocalAssets/` (gitignored, copied into the app as a
folder). See [LocalAssets/README.md](Ishara/LocalAssets/README.md): `holistic_landmarker.task`,
`asl-signs.tflite` (the ASL Signs model, decision D8; its thresholds ship in
`Resources/asl-bundle.json`), the older `SignCLIPEncoder` and `recognition-bundle.json`, and
`SampleSigns/*.mov` for the simulator (including `rest.mov` for calibration).

- With `asl-signs.tflite` the ASL model runs: a confident vocabulary sign is a chip, a fairly
  sure one a "Did you mean …?" tile that counts only when tapped, anything else **[?]**. When a
  hand left the picture during the sign or as it ended, the sign is always **[?]** with "a hand
  left the picture" (never a chip from a partial view); a hand dropped below the rest line is
  resting, even when a narrow portrait frame puts its wrist past the side edge.

- No recognition bundle or encoder: every accepted sign shows **[?]**. The app never guesses.
- Rejected attempts (too short, too long, lost tracking) produce no chip at all.
- The Core ML encoder always runs on CPU+GPU; the FP16 package is wrong on the Neural Engine.
- In the simulator, a **Replay a sign** menu on the camera area plays a saved clip (pipeline)
  or injects a result (scripted + live call), since there is no camera.
- On a device with the pipeline, Get ready, Signing and Speaking show a **live, mirrored
  front-camera preview** on the same capture session recognition reads (one preview layer,
  moved between screens), with tracking dots on shoulders and wrists and a dashed rest line
  once calibrated (the eye button hides them). Camera permission is asked on Get ready; if
  it's refused the card says so and offers **Open Settings**. Without a live camera
  (simulator, scripted results, fixtures) the card shows a placeholder.

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
| `-IsharaSampleSigns <folder>` | Simulator only. The replay menu plays the clips in this Mac folder (`rest.mov` for Get ready plus any `.mov`/`.mp4`/`.m4v`) instead of the bundled `LocalAssets/SampleSigns`, without a rebuild |
| `-IsharaFixture <name>` | Debug builds only. Opens a prepared state: `home`, `getReady`, `signing`, `speaking`, `delivered`, `notDelivered`, `ended`, `connectionLost`, `composing`, `stopped`, `stopTooLate`, `deliveredDespiteStop`, `backendError`, `endedNoCaptions`, `hangUpUnconfirmed` |

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

`LocalBackendCallUITests` walks the same call through the live driver against the
backend's free local demo server (no Bolna, nothing dialled). It is skipped unless you
start the server, point `Secrets.xcconfig` at it and pass the flag:

```sh
# backend/: uv run python -m scripts.local_demo --port 8799 --delay 0.3 > /tmp/local-demo.log
# Secrets.xcconfig: ISHARA_BACKEND_URL = http:/$()/127.0.0.1:8799, ISHARA_APP_TOKEN = ishara-local-demo
TEST_RUNNER_ISHARA_LOCAL_BACKEND=1 TEST_RUNNER_ISHARA_LOCAL_BACKEND_LOG=/tmp/local-demo.log \
  xcodebuild -project ios/Ishara.xcodeproj -scheme Ishara \
  -destination 'platform=iOS Simulator,name=iPhone 17' \
  -only-testing:IsharaUITests/LocalBackendCallUITests test
```

With the log path it also checks the stand-in Bolna spoke nothing before each SEND.

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
| `Packages/SignPipelineLiteRT` | LiteRT (TensorFlow Lite) runner for the ASL Signs model (iOS only; downloads its binary) |

"Call for me" (decision D9) is Home → **CALL FOR ME** → Get ready → Brief → the delegated call
→ Notes; it runs on the fake call in demo mode, and against the local demo backend in
`DelegatedCallUITests`.

## Still needs a device

- T1: install on the iPhone, grant camera permission, measure Holistic + model latency.
- The ASL model on portrait phone footage (the simulator parity used Lifeprint clips; see
  `docs/experiments/asl-model-probe.md`, Run 4).
