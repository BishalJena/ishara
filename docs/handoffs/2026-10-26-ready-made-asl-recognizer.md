# Handoff: the ready-made ASL recognizer, and the delegated-call mode (26–29 Oct)

Written 25 October 2026 for the teammate, revised the same evening after the measurements.
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
   `data.QUALITY` tracking minimums hold.
3. **Pick-one tile** when top-1 ∈ vocabulary and 0.35 ≤ p < 0.6: show the candidate; accept only
   on tap, or combine with the next attempt.
4. Otherwise `?`. A non-vocabulary top-1 at any confidence is `?` (the other 240 classes are the
   "something else" bucket; that is what keeps wrong words out).
5. Per-word thresholds are allowed (`tomorrow` 0.45 is the candidate) only after a labelled
   session shows zero wrong accepts at that value. Provisional values are flagged in the bundle
   exactly like `PROVISIONAL_BANNER` today.

Probe defaults and their evidence are in the record; the first labelled session is on the phone.

## What is built (25 Oct, evening) and what is left

Everything below is on this branch with tests; nothing has run against real Bolna or an iPhone.

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

### Left for you (teammate), in order

1. **LiteRT on iOS.** Wrap `model.tflite` (11 MB, from the Hugging Face mirror; ship it in the
   app bundle with its SHA-256 checked against the bundle's `model.sha256`) behind a
   `LogitsModel` in `SignPipeline`: input `[frames, 543, 3]` float32 in the **Kaggle layout**
   (face 468, left hand 21, pose 33, right hand 21; NaN for a missing part), output 250
   logits; `LogitsMatcher` does the rest. CocoaPods `TensorFlowLiteSwift` (Metal subspec
   optional) or Bazel; see R21. The Tasks Holistic Landmarker output must be re-ordered to
   that layout; `asl_model.kaggle_frame` is the reference. **Parity first:** the same 20
   saved cuts through Mac and simulator, compare top-1 and p (PLAN P3). If it slips, the
   demo runs recognition on the Mac bridge (D6 backup).
2. **Pick-one tile.** `LogitsMatchResult.pickOne` is produced by the matcher but the app's
   `SegmentClassifier` still maps results to `.sign` / `.unsure`; add a `.candidate(Sign)`
   recognition event, a tappable tile in `SigningPanel`, and accept only on tap.
3. **Brief and Notes screens.** Home: a "Call for me" button → profile fields (name,
   optional callback, reason) + the signed/tapped chips → `BackendClient.createBrief` →
   show `Brief.text` with "Approve and call" (attended toggle) → `startCall(StartCallRequest(
   mode: .delegated, briefID:, attended:))`. After `status ended`, `notes(callID:)` →
   a Notes screen: outcome, summary bullets, open questions, transcript, Bolna summary.
4. **Framing guard.** Warn when a hand is out of frame for > 0.3 s during a sign (portrait
   is narrow: simulated 9:16 cropping dropped `no` 0.64 → 0.42); say "hand left the frame"
   as the `?` reason.
5. **Thursday, iPhone:** 8 words × 5 attempts, guided, portrait (`live_probe.py --portrait`
   on the Mac is the rehearsal). Then freeze the bundle's thresholds from that session and
   set `provisional: false`.
6. **Real Bolna call** of the delegated flow to a consenting teammate, after the founder's
   go-ahead and a cost heads-up: the welcome message is Bolna's static disclosure; the
   opening goes out as a `user_reply` event right after `in-progress`, so watch for a
   `not_delivered` if Bolna is still speaking (B24) and re-send once by hand if so.

## Thursday (iPhone): the one measurement that matters

8 words × 5 attempts, guided prompt, portrait, phone at the distance a user holds it, same
decision rule. This is simultaneously the product-condition test, the landmarker parity check
(G3) and the number for the slide. Gate: ≥ 6/10 per script sign counting one-tap pick-one, 0 wrong
auto-accepts, 0 auto-accepts on negatives, < 2 s. Then freeze thresholds (and any per-word value)
from this session only and set the bundle's `provisional` to false.

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

## Open questions for you (teammate)

1. CocoaPods in the iOS project for LiteRT: acceptable, or Bazel, or Mac bridge for the demo?
2. Tasks Holistic Landmarker on iOS: confirm it exposes face (468), pose (33) and both hands (21)
   in a form we can re-order to the Kaggle layout, and what it reports for a missing hand.
3. D9: do you see a problem with an "ask the user" node waiting on an injected event in the graph
   agent? If the graph can't wait, the fallback is a backend-driven custom-LLM node like today's.

## Claim ledger

Rows R18–R24 and B29 in [CLAIM-LEDGER.md](../CLAIM-LEDGER.md#recognition-data-and-decision-models)
hold the sources and evidence limits: ASL Signs corpus and CC-BY (R18), the 1st-place model (R19),
SignCLIP-ASL (R20), LiteRT on iOS (R21), ASL Citizen not used (R22), "ISL and ASL overlap" measured
per word (R23), the 25 Oct probe results (R24), Bolna call summary on every call (B29).
