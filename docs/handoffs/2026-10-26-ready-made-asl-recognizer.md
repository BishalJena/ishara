# Handoff: the ready-made ASL recognizer, and the delegated-call mode (26–28 Oct)

Written 25 October 2026 for the teammate, revised the same evening after the measurements,
on 27 October after the simulator-side work landed (see [Built on 27 Oct](#built-on-27-oct-the-mac-only-list)),
and on 28 October after the first real calls (see [28 Oct](#28-oct-real-calls-and-what-changed)).
Supersedes the recognition track (R1–R4, G2) of [PLAN.md](../../PLAN.md); decisions D8 and D9
point here. Everything else in the plan (Bolna Path B, composer, call safety, iPhone gates) stands.

## The decision, in one paragraph

**The demo is pure ASL.** The recognizer is the public **Kaggle ASL Signs 1st-place model**
(1D-CNN + Transformer, 11 MB TFLite, MIT code, CC-BY corpus of ~94k phone-camera clips from 21
Deaf signers), used **as is**: no recording of our own data, no training, no fine-tuning, no
reference clips, no enrollment. We measured it on 25 Oct
([record](../experiments/asl-model-probe.md)): 6 of 11 Lifeprint ASL clips right at 0.70–0.94,
four of the presenter's signs right on the first attempt, confident-when-right and flat-when-not,
4 ms per sign, 0 wrong accepts at p ≥ 0.6. ISL is the product goal and is blocked by data
(INCLUDE ≈ 16 clips/word, none for yes/no/sorry); we measured which ISL signs the model happens
to share (thank you, the wave hello, the hand-form yes) and decided **not** to mix languages in
the demo. The pitch says all of this plainly.

## 28 Oct: real calls, and what changed

- **Real calls passed.** After five root-caused fixes (#80, #81, #82, #85 and verifying the
  number on the Bolna trial account), Live mode and all three Call-for-me flows passed on real
  Bolna calls, end to end from the simulator app with sign videos as the camera (#89, #90).
  [Voice record](../experiments/voice.md#runs), [status](../status/2026-10-28.md).
- **Chips:** only **hello, thankyou, yes, no, now, please, tomorrow, wait** can become a chip or
  a tile, at provisional cut-offs from the public-clip Gate 2 (#66): global p 0.65, per word
  0.45–0.6, margin 0.3, pick-one 0.35 (#83). Every other gloss is `?` at any confidence.
  That public-clip run failed for `yes` and `hello` (they miss on public signers), so the
  presenter's phone clips decide whether they stay.
- **MORNING is out** of the chip vocabulary: the model learned the one-handed form (one flat
  hand rising from the belly to stand upright beside the face), not the two-handed dictionary
  form. It can still be tapped. The iPhone test of the one-handed form decides
  ([issue #72](https://github.com/BishalJena/ishara/issues/72)).
- **Call for me:** an open "when?" question gets a TOMORROW / MORNING / NOW / WAIT card (#87);
  the opening shows as the agent's caption and an ask names the time actually offered (#93);
  the ask card keeps the camera in view (#95).
- **Framing hint:** also fires when a one-handed sign's hand leaves the picture as the sign
  ends (#94).

The tables further down are kept as written on 25–27 Oct; where they say p ≥ 0.6 or list
morning as a candidate, the bullets above win.

## What changed since the morning version

| Was planned | Now |
|---|---|
| Day 1 bake-off between model A (TFLite) and model B (SignCLIP-ASL) | **Done, A wins by default**: it works zero-shot and SignCLIP-ASL would need references or its text encoder. B is dropped unless A fails on the phone. |
| ISL-overlap test | **Done**: thankyou 7/8, hello (wave) 7/9, yes (hand) 1/1 shared; everything else not. Pure ASL chosen anyway. |
| Vocabulary from the 250 | **Measured**: solid = hello, thankyou, yes, no, now, please, tomorrow; candidates = morning, wait; dropped = sick, time. |
| Live mode only | **New D9 (approved, built)**: a *delegated call* mode, where the user signs the intent, approves a brief once, and the Bolna agent makes the call; optionally attended with yes/no/wait steering. |

## Vocabulary and script

The app accepts **any of the 250 glosses** that clears the decision rule; nothing is hard-coded
except the gloss list that ships with the model. The eight words below are the ones we rehearse
and promise on stage because they are measured:

| Role | Words | Evidence (reference / presenter) |
|---|---|---|
| Solid | hello, thankyou, yes, no, now ("today"), please, tomorrow | ≥ 0.70 on Lifeprint or ISLRTC; presenter 0.95 / (shared form) / 0.91 / 0.64 / 0.93 / 0.95 / top-1 17 of 21 at 0.3–0.66 |
| Candidates | morning, wait | presenter 0.62 once; Lifeprint 0.88 in a window. Decide on the phone session. |
| Dropped | sick, time | flat or wrong for both references and presenter |
| Untested but in the 250 | yesterday, later, night, can, where, who, why, have, finish, callonphone, hungry, drink, water, home, go, see, hear, read | available for free; don't promise them |

Live-mode script: **hello** → (call purpose supplies "doctor's appointment") → receptionist offers a
slot → **no** → **tomorrow · please** → "10:30 tomorrow morning?" → **yes** → **thankyou**.

## Decision rule (open set), to be implemented identically in Python and Swift

1. Full 250-way softmax over the model's logits. **Never restrict to the vocabulary first**
   (restricting first turned ISL `evening` into `no` 6/7 at p ≈ 0.01).
2. **Chip** when top-1 ∈ vocabulary, p ≥ 0.6, margin over the runner-up ≥ 0.3, and
   `data.QUALITY` tracking minimums hold. *(28 Oct: the shipped bundle uses p ≥ 0.65 globally
   with per-word values 0.45–0.6, still provisional, #83.)*
3. **Pick-one tile** when top-1 ∈ vocabulary and 0.35 ≤ p < 0.6: show the candidate; accept only
   on tap, or combine with the next attempt.
4. Otherwise `?`. A non-vocabulary top-1 at any confidence is `?` (the other 240 classes are the
   "something else" bucket; that is what keeps wrong words out).
5. Per-word thresholds are allowed (`tomorrow` 0.45 is the candidate) only after a labelled
   session shows zero wrong accepts at that value. Provisional values are flagged in the bundle
   exactly like `PROVISIONAL_BANNER` today.

Probe defaults and their evidence are in the record; the first labelled session is on the phone.
The rule is implemented three times against the same bundle and tested to agree: Python
(`asl_matcher.asl_decision`), Swift (`LogitsMatcher`), and the threshold sweep in `asl_summary.py`.

## What is built (25 Oct, evening) and what is left

Everything below is on this branch with tests; nothing has run against real Bolna or an iPhone.
**Deadline for all of it: Wednesday 28 Oct.** Thursday and Friday are rehearsal and slide only.

| Done | Where | Verified |
|---|---|---|
| ASL model as a `live_source` matcher with the open-set rule; `--model asl` on `live_source.py`, `mac_bridge.py`, `scripts/sign_lab.sh` | `spikes/recognition/asl_matcher.py`, `asl_model.py`, `asl_model_server.py`, `fixtures/asl/asl-bundle-provisional.json` (bundle v2: glosses, vocabulary, thresholds, `provisional: true`) | 14 rule tests; Lifeprint clips through the detector: no 0.95, tomorrow 0.74 chips |
| Backend vocabulary: 12 template signs + 22 ASL glosses, validator meanings, plain template sentences, `now` = today, issue #34 | `backend/app/protocol.py` (`TEMPLATE_SIGNS`, `ASL_SIGNS`), `validator.py`, `templates.py` | 874 backend tests |
| D9 delegated call: `POST /briefs`, `POST /calls` `mode=delegated` (+`attended`), agent opens with the brief after the disclosure, answers from the custom-LLM listen node (Groq brain, rule brain fallback, every line checked), `ask`/`answer`/`ask_resolved`, 10 s timeout → callback line, hang-up when done, `GET /calls/{id}/notes` | `backend/app/delegate.py`, `calls.py`, `custom_llm.py`, `protocol.py` | 21 tests + an end-to-end Sign Lab test with the scripted receptionist |
| Mac bridge: `--delegated [--attended] --name --brief-chips`, shows the agent's question, answers by sign or `a yes|no|wait` | `spikes/recognition/mac_bridge.py` | bridge tests |
| iOS: `Sign`/`SignLabel` carry the 34 backend signs; `StartCallRequest.mode/briefID/attended`, `BriefRequest`, `Brief`, `CallNotes`, `ask`/`ask_resolved`/`answer` messages; `BackendClient.createBrief/notes/startCall(_:)`; `TurnStore.openQuestion`, `answer`, `answerIfAsked`; `LogitsBundle` + `LogitsMatcher` (same rule, same fixture); `AskCard` on the signing screen, a recognised yes/no/wait answers an open question | `ios/Packages/CallSession`, `ios/Packages/RecognitionCore/.../LogitsMatcher.swift`, `ios/Ishara/Views/Components/AskCard.swift`, `ActiveCallViewModel.swift` | CallSession 175, RecognitionCore 104, app 139 tests; app builds for the simulator |

**Try it on the Mac now** (free, nothing dialled):

```sh
scripts/sign_lab.sh --free --model asl                                   # live mode, ASL model, webcam
scripts/sign_lab.sh --free --model asl -- --delegated --attended --name "Asha"   # D9: the agent calls, asks you yes/no
```

In the delegated run the scripted receptionist offers "4 pm tomorrow"; the bridge prints
the agent's question; sign **yes** or type `a yes`, and the agent says "Yes, 4 pm tomorrow
works. Thank you." Add `--brief-chips tomorrow morning` to change the brief; drop
`--attended` for the unattended version (the agent promises a callback and hangs up).

### Built on 27 Oct: the Mac-only list

Everything that was on the Mac-and-simulator list is now on this branch, built and tested in
the simulator. Nothing below has run on an iPhone or against real Bolna.

| Was left | What landed | Verified |
|---|---|---|
| **LiteRT in the app** | `SignPipeline/KaggleLayout` (Holistic Landmarker → `[frames, 543, 3]`, NaN for a missing part, the 10 iris points dropped) and the `LogitsModel` protocol; a new package `SignPipelineLiteRT` wrapping Google's prebuilt LiteRT C library (the binary behind the `TensorFlowLiteC` 2.17.0 pod, used directly because the iOS runtime is CocoaPods-only and this project is Swift packages only); `asl-signs.tflite` in `LocalAssets`; the shipped `Resources/asl-bundle.json`; `SegmentClassifier` runs the ASL engine whenever the model is installed (SignCLIP stays as the fallback) | Runtime: the iOS logits match the Mac runtime on a fixed input to < 0.001 with the same top-5; ≈ 15 ms per 1.5 s clip in the simulator. Its symbols don't overlap MediaPipe's embedded TensorFlow Lite (checked with `nm`), and the app links both. |
| **Parity in the simulator** | `IsharaTests/ASLParityHarness` runs saved clips through the app's own path (Holistic Landmarker task → LiteRT) and writes what it saw; `spikes/asl_probe/parity.py` runs the Mac path (legacy Holistic → the same model) on the same clips and compares | 18 Lifeprint ASL clips: on all 9 clips the Mac is confident about, the app gives the same top-1 and the same chip (no ×2, now ×2, tomorrow ×2, please, wait, yes); decisions agree on 17/18, the one difference being Mac `?` vs app "did you mean MORNING?"; the Mac model on the app's landmarks reproduces the app's output exactly. [Evidence](../experiments/evidence/asl-model-probe/parity-simulator-lifeprint.json). |
| **Pick-one tile** | `RecognitionResult.candidate(Sign)`; a "Did you mean TOMORROW?" tile under the camera on the call and brief screens; it becomes a chip, or answers the agent's question, only when tapped; the next sign or ✕ drops it | app tests |
| **Brief and Notes screens** | Home → **CALL FOR ME** → Get ready → Brief (sign or tap the day and time, name / callback / reason, "Prepare the request" → the backend's brief, "I'll stay and answer questions" switch, "Approve and call") → the call screen without SEND, chips or quick replies (the camera and the question card only when attended) → "See the call notes" → outcome, what happened, still open, the brief, the transcript, Bolna's summary marked as possibly wrong. Editing anything after the brief was built hides it until rebuilt. The fake driver plays a delegated call too, so it works with no backend. | app and UI tests; **end to end against the real backend code** (`backend/scripts/local_demo.py`, scripted receptionist): the agent opened with the brief, asked, the tapped yes went out on the call, the notes said Booked |
| **Framing guard** | `RecognitionCore/FramingGuard`: a hand whose landmarks vanish while the pose's wrist is past the left, right or top edge for > 0.3 s explains the `?` ("A hand left the picture. Keep both hands inside the frame.") | unit tests on synthetic tracks; not yet on real portrait footage |
| **Probe export** | `spikes/recognition/asl_summary.py`: per-word table (chip, one-tap, `?`, wrong), the gate check, and suggested thresholds from a session (`--records` from the live probe, `--clips` for one clip per attempt, `--app` for the app path's view of the same clips); `--write-bundle` writes the frozen bundle | tests, including that its rule matches `asl_decision` on 400 random vectors |

Also found and fixed on the way: a settled delegated call could open a second question if the
receptionist spoke again before the hang-up; it now says nothing new.

**Set-up for a fresh checkout** (once; nothing here is committed):

```sh
ios/Packages/SignPipelineLiteRT/Scripts/download_tflite_c.sh            # LiteRT, checksum-verified
ios/Packages/SignPipelineLiteRT/Scripts/download_asl_model.sh ios/Ishara/LocalAssets
ios/Packages/SignPipelineMediaPipe/Scripts/download_holistic_model.sh ios/Ishara/LocalAssets
```

`scripts/verify.sh` runs the first one itself. Without `asl-signs.tflite` the app falls back to
the old SignCLIP path; without the holistic model the pipeline can't start (Get ready says why).

### Left for the teammate (Mac and simulator)

*28 Oct:* items 1–4 are done: merged (#46), broken and fixed in the simulator (#64, #69, #70,
#89), deployed (#73, Heroku now runs `main` up to #93), demo script and slides (#55). What is
left on the Mac side:

1. **Rehearse** with the [demo script](../demo/SCRIPT.md) and the
   [runbook](../demo/RUNBOOK.md); record a backup video.
2. **Re-run the video-to-speech flows** after any change that touches the call:
   `scripts/e2e_video_to_speech.sh` (free, local) or `--rehearse` (deployed-mode test on
   `local_demo`); a real call (`--real --confirm-cost`) only after the founder's go.
3. Open issues worth fixing before the demo: #91, #96, #86.

The original list, for the record:

1. ~~**Review and merge this PR**; the rest builds on it.~~
2. ~~**Try to break it in the simulator**: the scripted demo (`CALL FOR ME` with the default fake
   call), the replay menu's `?`, `frame` and `tomorrow?` options, and the real backend code.~~
3. ~~**Backend deploy**, once the founder authorises it.~~
4. ~~**Demo script and slides.**~~

### Left for the founder (needs the iPhone)

*28 Oct:* item 4 is done (real delegated calls passed from the simulator). Items 1–3 still wait
for the device; the steps, simplified for whoever holds the phone, are
[issue #72](https://github.com/BishalJena/ishara/issues/72).

1. **Record the phone clips**, when the phone is available (next section). The iPhone's own
   Camera app is enough; the app does not need to be installed for this.
2. **Run them through both paths and freeze**: `asl_summary.py --clips` (Mac path) and the
   parity harness plus `asl_summary.py --app` (the phone's landmarker, in the simulator), then
   `--write-bundle`; review the result and ship it as `ios/Ishara/Resources/asl-bundle.json`
   (and `fixtures/asl/`). Until then the app says the thresholds are provisional.
3. **Install on the iPhone** for what only the device can show: live camera, frame rate and
   chip latency (PLAN G4).
4. ~~**The first real delegated call**~~ (done 28 Oct) to a consenting teammate, after a cost heads-up. It doesn't
   need the iPhone: the simulator or the Mac bridge can start it against the deployed backend.
   The opening goes out as a `user_reply` event right after `in-progress`, so watch for a
   `not_delivered` if Bolna is still speaking (B24) and re-send once by hand if so.

## The phone clips: the one measurement still missing

**What:** the 8 chip words (hello, thankyou, yes, no, now, please, tomorrow, wait) × 5
attempts, the one-handed MORNING × 10, plus 5 negatives (scratch your face, wave
vaguely, rest your hands), each a separate short video from the iPhone **front camera, portrait**,
held where a user would hold it; rest, sign once, rest. Name them `<word>_<n>.mov`
(`tomorrow_3.mov`, `none_2.mov`) and AirDrop them to the Mac. About 15 minutes.

**Then, on the Mac:**

```sh
cd spikes/recognition
.venv/bin/python asl_summary.py --clips ~/phone-clips --markdown /tmp/mac.md        # Mac path
TEST_RUNNER_ISHARA_PARITY_CLIPS=~/phone-clips TEST_RUNNER_ISHARA_PARITY_OUT=/tmp/app \
  xcodebuild test -project ../../ios/Ishara.xcodeproj -scheme Ishara \
  -destination 'platform=iOS Simulator,name=iPhone 17' -only-testing:IsharaTests/ASLParityHarness
.venv/bin/python ../asl_probe/parity.py --clips ~/phone-clips --sim /tmp/app       # path parity
.venv/bin/python asl_summary.py --app /tmp/app --write-bundle /tmp/asl-bundle.json  # app path, frozen bundle
```

Convert anything that isn't H.264 first (`ffmpeg -i in.mov -c:v libx264 out.mp4`): the simulator
could not decode VP9. **Gate:** ≥ 6/10 per script sign counting a correct one-tap pick-one, 0 wrong
auto-accepts, 0 auto-accepts on negatives. The suggested cut-off never goes below the bundle's
0.6 globally; per-word values only go down (not below 0.45) where they add right chips and no
wrong one. *(28 Oct: the provisional bundle already uses 0.65 globally with per-word values
from the public clips, #83; the phone clips replace them.)* Latency (< 2 s) is measured on the device, not in the simulator.

## D9 (approved 25 Oct, built): the delegated call, with optional steering

**What it is.** The user signs the intent (`tomorrow · morning`, or taps it), the app builds a
**brief** from the chips plus the user's profile (name, optional callback number, reason), shows
it, and the user approves it **once** by starting the call with its id. The agent then places
the call and pursues only the brief: after Bolna's static disclosure it states the request
itself, answers the receptionist from the custom-LLM listen node (Groq brain with a rule-based
fallback; every line is checked for invented numbers, names, times and booking claims and
replaced by the rule brain's line if it fails), and hangs up when the brief is settled.
Afterwards `GET /calls/{id}/notes` gives the transcript, a deterministic summary that quotes
the transcript, the outcome (booked / declined / callback / unclear / no_answer), open
questions, and Bolna's own call summary when its webhook carried one.

**Two ways to run it, chosen at dial time (`attended`):**

- *Unattended:* phone down, notes later. Any concrete offer or out-of-brief question →
  "I'll need to check that and call back. Thank you.", then the agent hangs up (6 s later).
- *Attended:* captions stream live. When the receptionist proposes a time, the agent says
  "One moment, please." and the app shows the question with three options, each with the
  exact sentence the agent will say: **yes** ("Yes, 4 pm tomorrow works. Thank you."), **no**
  ("No, 4 pm tomorrow doesn't work, sorry. Is there another time?"), **wait** (holds the line,
  timer restarts). The user signs or taps; the answer goes out through the verbatim speak node
  like a SEND (`turn_id` `ask-…`). No answer within 10 s → the callback line.
  *28 Oct (#87):* an open "when?" question with no time in it gets the time words instead:
  **tomorrow**, **morning**, **now** (each "…, please. What times are available?") and **wait**;
  morning is tap-only while it can't chip.

The existing verbatim **live mode** stays as the third option for personal calls.

**Safety that carries over.** One explicit approval of the brief before dialling; Bolna's
disclosure that it is calling on behalf of a Deaf user; the agent may only pursue the brief and
never commits outside it; transcript shown next to the summary; allowlisted consenting
recipients only; a real call still needs the founder's go-ahead and a cost heads-up (PLAN §10).

**Messages (backend/app/protocol.py, mirrored in CallSession/Messages.swift):** `POST /briefs`
(`BriefRequest` → `BriefResponse`), `POST /calls` with `mode`, `brief_id`, `attended`;
WebSocket `ask` {ask_id, question, options[{choice, spoken}], fallback, timeout_s},
`answer` {ask_id, choice}, `ask_resolved` {ask_id, spoken, source: user|timeout};
`GET /calls/{id}/notes` → `CallNotes`.

## Rules for this track

- **No training, no fine-tuning, no ASL Citizen download, no Gemini in the call path.**
- Public clips are fetched for local evaluation or learning only; nothing third-party is committed.
- A wrong word is worse than no word: auto-accept stays at zero wrong on everything measured;
  uncertainty shows as pick-one or `?`. Never restrict the softmax to the vocabulary first.
- Pitch wording, every time: *"a published, signer-independent ASL model trained on public data
  from 21 Deaf signers; the presenter is hearing and learned the signs from Lifeprint; ISL is the
  goal and is blocked by data, which is the problem we want to solve; nothing is spoken on a call
  without the user's approval; no Deaf-user validation yet."*

## Open questions for the teammate

1. ~~CocoaPods for LiteRT?~~ Answered: neither CocoaPods nor Bazel; the pod's prebuilt C
   library as a Swift package binary target (see the package's `Package.swift` and download script).
2. ~~Does the Tasks Holistic Landmarker fit the Kaggle layout?~~ Answered: 478 face points (the
   first 468 are the layout), 33 pose, 21 per hand, an empty list for a missing part; left and
   right hands land on the same sides as legacy Holistic in all 18 parity clips.
3. D9: the backend drives the "ask the user" step from the custom-LLM listen node (it holds the
   line while an answer is pending), so the graph never waits on an event. Worth a look before
   the first real call: what Bolna does when an injected `user_reply` arrives while the
   receptionist is still talking (B24).

## Claim ledger

Rows R18–R24 and B29 in [CLAIM-LEDGER.md](../CLAIM-LEDGER.md#recognition-data-and-decision-models)
hold the sources and evidence limits: ASL Signs corpus and CC-BY (R18), the 1st-place model (R19),
SignCLIP-ASL (R20), LiteRT on iOS (R21), ASL Citizen not used (R22), "ISL and ASL overlap" measured
per word (R23), the 25 Oct probe results (R24), Bolna call summary on every call (B29).
