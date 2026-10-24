# Evidence: iOS visual review (24 Oct 2026)

A screen-by-screen review of the iOS app on `main @ 54b1c50`, before the fixes in PRs
#37–#40. The findings (F1–F19, polish P1–P6) are in [REPORT.md](REPORT.md); how each
high and medium finding was fixed and re-checked is in
[the verified fixes](../ios-fixes-verified-24oct/README.md). Method and pass rules for
this kind of review: [TESTING.md](../../../TESTING.md#ios-visual-review).

**Executed** on the development Mac: Xcode 27.1, iOS 27.0 simulators (iPhone 17 and
iPhone 17e), status bar fixed at 9:41. Nothing was dialled and no paid API was used.

| Run | How | Result |
|---|---|---|
| Fixture states | `xcrun simctl launch booted ai.ishara.demo -IsharaFixture <state>` then `xcrun simctl io booted screenshot`, in light, dark and accessibility-large (AX-L) text, on iPhone 17 and 17e | 30 screenshots |
| Walked demo call, 1× | a throwaway UI test (not committed) that taps through the PLAN §1 call on the fake driver and screenshots every moment | `testFullFlow` passed (65 s), 33 frames |
| Walked demo call, 0.5× and side paths | the same test with `-IsharaFakeTimeScale 0.5`, plus throwaway tests for STOP mid-sentence, not delivered → re-SEND and the Dr. Mehta contact | 4 / 4 test cases passed, 33 + 13 frames |
| Empty name | Home with no name typed | 1 screenshot |

All images are downscaled JPEGs (800 px tall for screens, 1000 px wide for contact
sheets) to keep the folder small; the originals stay local.

## Files

| File | What it shows | Finding |
|---|---|---|
| [REPORT.md](REPORT.md) | The review: findings, severity, cause with file and line, suggested fix | all |
| `shots/fixtures-light/` (8) | One screenshot per fixture state: `home`, `getReady`, `signing`, `speaking`, `delivered`, `notDelivered`, `ended`, `connectionLost` | F1 (`ended`), F2 (`getReady`), F9 and P3 (`home`), F18 (`delivered`), F19 (`signing`) |
| `shots/fixtures-dark/` (8) | The same states in dark mode | F1 (`ended`), F10 (`signing`) |
| `shots/fixtures-axl/` (8) | The same states at accessibility-large text | F1 (`ended`), **F3** (`signing`, `notDelivered`, `speaking`), F14 (`signing`, `getReady`) |
| `shots/fixtures-17e/` (6) | iPhone 17e at default text: `home`, `signing`, `speaking`, `delivered`, `notDelivered`, `ended` | none: every screen fits |
| `shots/flow-scale1/01-home` … `33-home-after` (33) | The whole §1 call at 1×: Get ready (02–05), dialing, ringing, in call (06–08), turn 1 chips → draft → speaking → delivered (09–15), caption (16), turn 3 with the wrong chip removed (17–23), caption (24), turn 5 with `?` (25–29), quick reply (30), Clear (31), ended (32), back home (33) | F1 (32), F2 (02–05), F5 (30 → 31), F6 (10–13, 18, 20), F8 (08, 14), F11 (17), F12 (14, 22), F13 (23, 27, 28), F15 (25), P5 (24, 29) |
| `shots/flow-scale0.5/28-t5-delivered.jpg` | The 0.5× run caught mid cross-fade | F13 |
| `shots/stop/` (3) | STOP while speaking, then the result | **F7** |
| `shots/notdelivered/` (5) | Not delivered (`-IsharaFakeNotDelivered YES`) → tap SEND again → delivered | none: works as designed |
| `shots/mehta/` (5) | The second contact, Dr. Mehta's office, on the fake driver | F9 (02), F17 |
| `shots/misc/01-home-empty-name.jpg` | Home with the name empty: CALL grey with no reason | F16 |
| `contact-sheets/f1-a` … `f1-h` | The 1× flow, 4 frames per sheet, in order (`f1-a` = Get ready) | as `flow-scale1/` |
| `contact-sheets/F-ab` … `F-gh` | The same flow, 8 frames per sheet | as `flow-scale1/` |
| `contact-sheets/f05-a`, `f05-b` | The 0.5× flow | F13 |
| `contact-sheets/light-a`, `dark-a`, `dark-b`, `axl-a`, `axl-b`, `17e-a`, `17e-b` | Fixture states side by side per appearance and device | F3, F10, F14 |
| `contact-sheets/SN`, `sn-top`, `sn-bot`, `stop`, `nd` | STOP, not delivered, Home with the second contact, ended | F1, F7, F9 |
| `contact-sheets/mehta1`, `mehta2` | The Dr. Mehta run | F17 |
| `contact-sheets/qr-crop` | Dark-mode quick replies, cropped | F10 |
| `appshell-pr22/` (8) | Earlier capture of the four screens when the app shell landed (PR #22): `home`, `getReady`, `signing`, `speaking`, each at default and AX-L | baseline only |

## Left out on purpose

- `loop-scale1/` (58 timed frames of the same 1× flow) and 32 of the 33 0.5× frames:
  they repeat the named frames.
- Build and test logs: they contain local machine paths and simulator ids, and the
  pass counts are recorded above.
- The throwaway review UI test and the scratch copy of `ios/` it ran in.
