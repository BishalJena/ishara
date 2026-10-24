# Evidence: iOS review fixes, verified (24 Oct 2026)

Before/after screenshots for the high and medium findings of the
[24 Oct visual review](../ios-visual-review-24oct/README.md), fixed in PRs #37–#40.
**Executed** on the development Mac, Xcode 27.1, iOS 27.0 simulators (iPhone 17 and
17e), status bar fixed at 9:41. The "after" shots are Debug fixtures
(`-IsharaFixture <state>`), at default text and at accessibility-large (AX-L,
`-UIPreferredContentSizeCategoryName UICTContentSizeCategoryAccessibilityL`). Nothing
was dialled and no paid API was used.

In `pairs/` the **left frame is before** (from the review folder) and the frames to its
right are after. All images are downscaled JPEGs.

## Finding → fix → evidence

| Finding | PR | Screenshot(s) | Verdict |
|---|---|---|---|
| **F1** transcript wiped on End | #38 | [`pairs/F1-transcript-kept.jpg`](pairs/F1-transcript-kept.jpg) (before: placeholder after End; after: `state-ended` keeps the receptionist line and the "Ishara (voice)" goodbye, `state-endedNoCaptions` says "No captions in this call.") | **Fixed.** Seen in the screenshot; `swift test` CallSession 164 / 164 with tests for the transcript kept on End and late events ignored |
| **F2** no camera view, spec text in the placeholder | #39 | [`pairs/F2-camera-card.jpg`](pairs/F2-camera-card.jpg), `after/camera-getReady.jpg`, `camera-signing.jpg`, `camera-speaking.jpg`, `camera-signing-axl.jpg` | **Fixed in the simulator only.** The placeholder now reads "Camera preview appears on your iPhone." The live mirrored preview, permission prompt and Open Settings path need a camera: **check in T1** on the iPhone. 121 unit tests (session sharing, permission mapping, card selection, overlay mapping); the device build compiles |
| **F3** draft hidden under SEND at AX-L (safety) | #40 | [`pairs/F3-signing-axl-17.jpg`](pairs/F3-signing-axl-17.jpg), [`F3-speaking-axl-17.jpg`](pairs/F3-speaking-axl-17.jpg), [`F3-notdelivered-axl-17.jpg`](pairs/F3-notdelivered-axl-17.jpg); all of `after/layout-{17,17e}-*-{default,axl}.jpg`; sheets [`after/sheet-layout-17e-axl.jpg`](after/sheet-layout-17e-axl.jpg) and the other three `sheet-layout-*` | **Fixed.** The sentence sits right above SEND or STOP on both phones at default and AX-L. The UI test asserts the draft is fully on screen above SEND at every SEND (default and AX-L), and a fixture test checks AX-L and AX-XXXL. 139 unit, 4 UI tests (1 skipped: the local-backend test). Left over: at AX-L the "Not delivered" banner can scroll off screen; the orange badge beside SEND stays visible |
| **F4** backend errors never shown (too-late STOP, unconfirmed hang-up) | #38 | [`pairs/F4-error-states.jpg`](pairs/F4-error-states.jpg): `state-stopTooLate`, `state-deliveredDespiteStop`, `state-hangUpUnconfirmed`, `state-backendError` (all after; the review found this in code, no before shot) | **Fixed in the app.** Shown from fixtures; the real `cannot_interrupt` and `end_failed` from Bolna have not happened on a live call yet (V4) |
| **F5** old "✓ Delivered" came back after quick reply + Clear | #38 | none (before: [`../ios-visual-review-24oct/shots/flow-scale1/31-after-clear.jpg`](../ios-visual-review-24oct/shots/flow-scale1/31-after-clear.jpg)) | **Fixed, tests only.** TurnStore tests: a chip or quick reply dismisses a delivered result; Clear dismisses an unspoken reply |
| **F6** empty prompt while a draft is composing | #38 | [`pairs/F6-composing.jpg`](pairs/F6-composing.jpg) | **Fixed.** "Composing…" with a spinner while chips wait for their draft |
| **F7** a deliberate STOP looked like a failure | #38 | [`pairs/F7-stopped.jpg`](pairs/F7-stopped.jpg) | **Fixed.** "Stopped. Nothing was spoken." with a "Stopped" badge; "Not delivered — tap SEND again" stays for the no-confirmation case |
| **F8** disclosure, holding line and goodbye invisible | #37 (backend), #38 (app) | [`pairs/F8-agent-lines.jpg`](pairs/F8-agent-lines.jpg) (before: empty feed in call; after: goodbye as "Ishara (voice)") | **Fixed.** The backend sends these as `caption {speaker: "agent"}` (tests: disclosure once per call, holding line on every silence, goodbye only after `end_call` reached Bolna); the app UI test checks the disclosure at the start and the goodbye after End. On a real Bolna call: not yet (V4) |
| **F9** "Path B" jargon, disclosure only on Home | #40 | [`pairs/F9-disclosure.jpg`](pairs/F9-disclosure.jpg) (Home before; Home and Get ready after) | **Fixed.** "Calls are placed from Ishara's calling number, not your own number. The receptionist hears an automated voice reading what you approve." on Home and on Get ready; the walked UI test checks both |
| F12 stuck-looking progress bar on Speaking | #40 | `after/layout-*-speaking-*.jpg` | **Fixed** (bar removed to give the sentence room) |

Still open from the review (not touched by #37–#40): F10, F11, F13–F19 and polish
P1–P6. They are low severity; see [REPORT.md](../ios-visual-review-24oct/REPORT.md).

## Files

| Folder | What |
|---|---|
| `pairs/` (10) | Before (left) and after, side by side, per finding |
| `after/state-*.jpg` (10) | PR #38 fixtures: `ended`, `endedNoCaptions`, `hangUpUnconfirmed`, `stopped`, `stopTooLate`, `deliveredDespiteStop`, `backendError`, `composing`, `delivered`, `signing` |
| `after/camera-*.jpg` (4) | PR #39 camera card on Get ready, Signing (default and AX-L) and Speaking; taken before #40, so `camera-signing-axl` still shows the old hidden draft |
| `after/layout-{17,17e}-{home,getReady,signing,notDelivered,speaking}-{default,axl}.jpg` (20) | PR #40 on both phones, both text sizes |
| `after/sheet-layout-{17,17e}-{default,axl}.jpg` (4) | The same, five screens per sheet (Get ready, Home, Not delivered, Signing, Speaking) |

## Left out on purpose

Intermediate layout attempts made while building #40 (`try1-*`, `try2-*`): they show
superseded layouts and would only confuse the record.
