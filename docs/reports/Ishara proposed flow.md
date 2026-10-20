# Ishara: proposed recognition and call flow

20 October 2026. Candidate composition, not an approved or validated architecture.

**Later execution update:** SignCLIP reference matching is now the leading
fresh-data candidate after a local comparison; OpenHands remains the baseline.
The diagrams below preserve the earlier proposal. See the
[current handoff](../HANDOFF.md) for demonstrated capabilities and unresolved gates.

[Open the editable Eraser diagrams](https://app.eraser.io/workspace/zVc3HKAZJoPNLIRzV2Ud).
Eraser reports this as a team file with link sharing disabled. Its privacy-update
tool failed, so owner-only access was not established. Eraser MCP uses OAuth in the
local client; credentials and account metadata are not part of this repository.

## User flow

1. The user starts an ordinary call, then explicitly opens Ishara and positions
   the camera. Phone calling remains preferred; WhatsApp is a separate diagnostic
   path from the existing plan.
2. The user signs a supported meaning, or deliberately types/selects an exact
   phrase. Early recognition can use explicit clip boundaries to isolate the
   classifier problem.
3. The recognizer proposes a label or abstains. A deterministic phrase composer
   uses supported meaning and explicitly supplied details to prepare draft text.
   A label such as `hello` cannot establish an appointment request or a date.
4. The user sees the exact sentence and approves it before speech. Uncertain input
   stays silent and offers retry, edit, or explicit phrase input.
5. A backend adapter submits that exact text to a Bolna speech session. The intended
   role is non-telephony speech orchestration with streaming, playback markers, and
   cancellation. This is an OSS integration candidate requiring engineering;
   hosted standalone speech access has not been established.
6. Audio returns to the iPhone. Apple's AAC injection path is a device feasibility
   gate: the recipient must hear the exact audio in the existing call while camera
   capture and captions remain usable.
7. The recipient replies through the same call. The user reads system Live Captions,
   where available, and chooses the next response. Ishara has no established access
   to the remote call audio or the system caption text.

Stop/cancel must clear pending generation and playback. A new session must not replay
an old utterance. Audio already heard cannot be retracted. Hanging up remains under
the user's native call controls.

## Recognition choice

The first design candidate is a normalized temporal pose model from OpenHands.
It must use its own training-matched landmark layout, temporal sampling, missing-data
handling, centering, and scaling. It is not a drop-in replacement for our current
134-value INCLUDE input.

Two alternatives remain:

- SignCLIP with verified ISL references and its own compatible preprocessing.
- An RGB temporal model where landmark extraction discards relevant detail.

These are alternative routes to select and evaluate, not an assumed three-model
ensemble. An acceptance policy needs input-quality evidence and unsupported-input
evaluation; a high softmax score alone is insufficient.

For the prototype, recognition can remain on the Mac. If camera input later comes
from the phone, clip/landmark transport is a separate integration step. On-device
recognition and the final component placement are undecided.

## What has and has not been established

- The current INCLUDE diagnostic harness runs. Its reused dataset and webcam clips
  are development evidence; none of the proposed replacement models has been tested
  on the intended seated setup.
- Bolna account access is not evidence of controllable speech output.
- A local Apple-voice control can isolate the device-audio question. It does not
  satisfy the mandatory Bolna integration.
- No end-to-end proof of camera, genuine Bolna speech, injected audio, and captions
  operating together exists.
- Failure of the preferred path prompts an explicit product decision. An app-owned
  or service-originated call would be a disclosed pivot, not automatic fallback.
- No natural-conversation or Deaf-user validation has occurred.

## Eraser source: conversation flow

Converted and updated from the earlier Mermaid flow in `docs/WORKFLOW.md`.

```eraser
direction right

User signs [icon: hand, color: green, label: "User signs a supported meaning"]
Recognize [icon: camera, color: blue, label: "Capture, recognize and compose draft"]
Preview [icon: file-text, color: blue, label: "Preview the exact sentence"]
Approve [shape: diamond, color: green, label: "User approves?"]
Retry [icon: repeat, color: orange, label: "Retry, edit or choose a phrase"]
Bolna [icon: volume-2, color: orange, label: "Bolna speech session - integration unproven"]
Inject [icon: smartphone, color: orange, label: "iPhone AAC injection - device gate"]
Call [icon: phone, color: blue, label: "Existing user-started Phone call"]
Recipient [icon: user, color: green, label: "Recipient hears speech and replies"]
Captions [icon: message-square, color: orange, label: "System captions visible to user - device gate"]
Start call [icon: phone-call, color: green, label: "User starts ordinary own-number call"]
Paused [icon: pause-circle, color: orange, label: "Pause output and clear pending speech"]

User signs > Recognize
Recognize > Preview: supported draft
Recognize > Retry: unsure or unsupported
Retry > Preview: explicit correction or phrase
Retry > User signs: re-sign
Preview > Approve
Approve > Retry: no
Approve > Bolna: exact approved text
Bolna > Inject: speech audio
Inject > Call
Start call > Call
Call > Recipient: outbound speech
Recipient > Captions: reply through same call, OS caption path
Captions > User signs: user reads and responds
Bolna > Paused: error or user cancel
Inject > Paused: injection unavailable or user cancel
```

## Eraser source: recognition routes

```eraser
direction down

Camera [icon: camera, label: "Camera frames and timestamps"]
Tracking [icon: activity, label: "Track hands and body; retain raw frames"]
Quality [shape: diamond, label: "Usable signing capture?"]
Retry [icon: repeat, color: orange, label: "No speech - improve framing or retry"]
Segment [icon: scissors, label: "One sign segment - explicit boundary first"]
Route [shape: diamond, color: purple, label: "Design choice: select ONE route"]

Leading candidate [color: blue] {
  Pose prep [label: "OpenHands training-matched pose preprocessing"]
  OpenHands [label: "OpenHands DPC or SL-GCN checkpoint"]
}

Alternatives to evaluate [color: purple] {
  SignCLIP [label: "SignCLIP-compatible pose plus verified ISL references"]
  RGB [label: "RGB temporal model with its own sampling and crops"]
}

Accept [shape: diamond, color: orange, label: "Supported and acceptable evidence?"]
Abstain [color: orange, label: "Unsure - retry or enter phrase explicitly"]
Compose [label: "Deterministic phrase from supported meaning"]
Preview [color: green, label: "Preview exact text; user edits and approves"]
Speech [color: orange, label: "Approved text to Bolna speech path"]

Camera > Tracking
Tracking > Quality
Quality > Retry: no
Retry > Camera
Quality > Segment: yes
Segment > Route
Route > Pose prep: primary research candidate
Pose prep > OpenHands
Route > SignCLIP: alternative
Route > RGB: alternative
OpenHands > Accept
SignCLIP > Accept
RGB > Accept
Accept > Abstain: no
Abstain > Camera: retry
Abstain > Preview: explicit phrase
Accept > Compose: yes
Compose > Preview
Preview > Speech: user approves
```

See the [recognition landscape](<ISL recognition landscape.md>),
[Bolna paths](<../research_notes/Ishara hackathon product directions/bolna-paths.md>)
and [phase plan](../../PLAN.md) for the evidence and implementation gates.
