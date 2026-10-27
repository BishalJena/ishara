# RecognitionCore

Pure Swift logic for on-device recognition (decisions D6 and D8 in [PLAN.md](../../../PLAN.md#2-decisions)):
the start/stop sign detector with rest calibration, and the matchers that turn one accepted sign
into a chip, a "did you mean" candidate or "unsure". No UIKit, AVFoundation or MediaPipe: the
app feeds it tracker results and model outputs. Behaviour follows
[PLAN.md §4](../../../PLAN.md#4-the-turn-when-signing-becomes-words) and the
[D8 handoff](../../../docs/handoffs/2026-10-26-ready-made-asl-recognizer.md).

```
Get ready (2 s hands down) ──▶ SignDetector.calibrate ──▶ restY
camera frame ──▶ DetectorFrame ──▶ SignDetector.update ──▶ .status(pill colour)
                                                       └─▶ .segment(start, end, accepted, reason)
accepted clip ──▶ ASL Signs model (LiteRT, in the app) ──▶ 250 logits ─┐
clip frames  ──▶ ClipQuality.from ────────────────────────────────────┴─▶ LogitsMatcher.match
                                                     ──▶ .chip / .pickOne / .unsure(reason)
unsure clip  ──▶ FramingGuard.handLeftFrame ──▶ "a hand left the frame" hint
```

The older SignCLIP path (`RecognitionBundle` + `SignMatcher`, personalised references) is kept
as the app's fallback when the ASL model is not installed.

| Type | Role |
|---|---|
| `LogitsBundle` | The version-2 ASL bundle (`ios/Ishara/Resources/asl-bundle.json`): the model's 250 glosses, the vocabulary that may become chips, the thresholds, `provisional`. Decoding validates it |
| `LogitsMatcher` | The open-set rule over all 250 classes, never narrowed to the vocabulary first; same rule and fixture as `asl_decision` in [`asl_matcher.py`](../../../spikes/recognition/asl_matcher.py) |
| `FramingGuard` | Explains a `?` when a hand vanished past the left, right or top edge for > 0.3 s |
| `SignDetector` | States watching / signing / cooldown / can't see. Hands above `restY` for 0.10 s start a clip (0.20 s pre-roll); 0.40 s back at rest end it; under 0.30 s or over 4 s is rejected; 0.50 s without shoulders drops it |
| `SignDetector.calibrate` | Rest line = median wrist height − 0.08, clamped to 0.50–0.95; 0.80 when no wrist is seen; fails `tooShort` (< 2 s) or `cantSee` (< 80% frames with shoulders) |
| `RecognitionBundle` | JSON from the Mac tool: references and frozen cut-offs. Decoding validates it |
| `SignMatcher` | Same rule as `rank` + `decision` in [`recognition_data.py`](../../../spikes/recognition/recognition_data.py) |

## Test

Needs full Xcode (the Command Line Tools have no XCTest):

```sh
cd ios/Packages/RecognitionCore
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer swift test
```

`swift build` works with the Command Line Tools alone. To run the same tests on
an iOS simulator (from this folder; `.build/` is ignored):

```sh
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcodebuild test \
  -scheme RecognitionCore -destination 'id=<simulator UDID>' -derivedDataPath .build/xcode
```

## Shared detector fixtures

`Tests/RecognitionCoreTests/Fixtures/detector/*.json` are run by
`DetectorFixtureTests`; every JSON file in that folder is checked. The Python
detector uses the same format, so its fixtures are copied in unchanged as
`py_<name>.json` (from `spikes/recognition/fixtures/detector/`); the files
without the prefix were written for this package:

```json
{"name": "...", "params": {"pre_roll_s": 0.0},
 "calibration": [{"t": 0.0, "body": true, "wrists": [[0.4, 0.85]]}],
 "frames": [...],
 "expected_rest_y": 0.77, "expected_calibration_error": null,
 "expected_segments": [{"start": 0.8, "end": 2.0, "accepted": true, "reason": null}],
 "expected_statuses": ["watching", "signing", "watching"]}
```

`params` overrides use the snake_case spec names; unknown names fail the test.
A fixture whose calibration fails has no `frames`. Statuses include the first
`watching`, which the detector reports on its first frame.

## Timing rule

"Continuously for at least X" accepts a run 1e-9 s short of X, so frame times
that sum to X with rounding error still count. Length limits (0.30 s, 4 s) and
the 2 s calibration coverage compare exactly. The Python detector does the same.
