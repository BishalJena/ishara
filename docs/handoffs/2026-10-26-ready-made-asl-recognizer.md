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
| Live mode only | **New D9 (proposed)**: a *delegated call* mode, where the user signs the intent, approves a brief once, and the Bolna agent makes the call; optionally attended with yes/no/wait steering. |

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

## Day 1 (Mon 26 Oct): recognizer into the pipeline (Mac), composer, UI

1. **Adapter in the recognition spike.** `spikes/asl_probe/asl_model.py` already gives
   `kaggle_frame(result)` (legacy Holistic → `[543, 3]`, NaN for missing) and `AslModel.predict`
   via a subprocess in `artifacts/asl_signs/.venv` (the main `.venv` is uv-managed and must not
   get TensorFlow). Promote it to `spikes/recognition/asl_matcher.py` as a second `Matcher` for
   `live_source.py` / `mac_bridge.py`, selected by `--model asl`; `Match.similarity` carries the
   probability, `Match.top` the top-3 glosses. `live_probe.AslMatcher` is the reference.
   *Done:* `scripts/sign_lab.sh --model asl` shows chips from the webcam with the real composer.
2. **Bundle format v2** for the app: `{"model": "asl-signs-1st-place", "model_sha256", "glosses":
   [250], "vocabulary": [...], "thresholds": {"p", "margin", "pick_one_p"}, "per_word": {...},
   "quality": data.QUALITY, "provisional": bool}`. No reference embeddings any more.
   `RecognitionBundle.swift` and `SignMatcher.swift` read it; `SignMatcher` becomes "argmax over
   250, then the rule above". *Done:* Swift tests for chip / pick-one / `?` / non-vocab.
3. **Composer accepts the model's glosses.** `backend/app/protocol.py`, `validator.py`,
   `templates.py`, `ios/Packages/CallSession/.../Vocabulary.swift`, `RecognitionCore/.../SignLabel.swift`,
   `recognition_data.VOCABULARY`: the label set comes from the bundle's `glosses` ∩ a service-call
   allowlist (the 8 + candidates + the "untested but plausible" list). `now` means today; `please`
   is politeness, not a fact. Fix issue #34 while there. *Done:* 813+ backend tests green, Swift
   packages green.
4. **UI:** pick-one tile (two tappable candidates at most, nothing auto-selected), yes/no/wait
   quick-reply buttons on the call screen. `?` stays `?`.
5. **Probe fixes** (for Thursday): big prompt banner, save an `.mp4` per cut, `--portrait`, per-word
   summary with ground-truth labels. Re-encode the ISLRTC clips on the lesson page to H.264 or drop
   them (pure ASL now); keep the Lifeprint cards.

## Day 2 (Tue 27 Oct): on device, and the delegated-call mode

1. **LiteRT on iOS.** CocoaPods `TensorFlowLiteSwift` (Metal subspec optional) wrapped as a
   `SignPipeline` encoder, or Bazel if CocoaPods is unacceptable in the SwiftPM project. Input is
   the Tasks Holistic Landmarker output re-ordered to the Kaggle 543-point layout, NaN for missing
   parts. **Parity first:** run the same 20 saved cuts through Mac (legacy Holistic) and simulator
   /phone (Tasks Landmarker) and compare top-1 and p before trusting phone chips (PLAN P3). If
   LiteRT slips, the demo runs recognition on the Mac bridge (D6 backup, G3 fallback).
2. **Framing guard.** Portrait is narrow: simulated 9:16 cropping dropped `no` 0.64 → 0.42 and
   `tomorrow` 0.36 → 0.17 because hands left the frame. The Get-ready screen should show the rest
   line and warn when a hand is out of frame for > 0.3 s during a sign; the `?` reason should say
   "hand left the frame".
3. **D9, delegated call (proposed):** see below.
4. **Docs:** PLAN §1/§5/§6/§7, `docs/HANDOFF.md`, `README.md`, status snapshot. Credit Deaf
   Professional Arts Network, Georgia Tech, hoyso48 and the sign-language-processing mirror;
   Lifeprint for the lesson clips (local viewing only).

## Thursday (iPhone): the one measurement that matters

8 words × 5 attempts, guided prompt, portrait, phone at the distance a user holds it, same
decision rule. This is simultaneously the product-condition test, the landmarker parity check
(G3) and the number for the slide. Gate: ≥ 6/10 per script sign counting one-tap pick-one, 0 wrong
auto-accepts, 0 auto-accepts on negatives, < 2 s. Then freeze thresholds (and any per-word value)
from this session only.

## D9 (proposed): the delegated call, with optional steering

**What it is.** The user signs the intent (`doctor · tomorrow · morning` or taps it), the app
builds a **brief** from the chips plus the user's profile (name, DOB, clinic, callback number;
typed once), shows it, and the user approves it **once**. The Bolna agent then places the call and
pursues only the brief. Afterwards the app shows the **transcript and the Call Summary** (Bolna
runs a summary extraction on every call and posts it with the webhook; transcript via the
executions API). Anything the brief did not cover comes back as a question in the notes, never
as a commitment the agent made up.

**Two ways to run it, chosen at dial time:**

- *Unattended:* phone down, notes later. Out-of-brief questions → "I'll check and call back."
- *Attended:* captions stream live. At a decision point the agent says "One moment, please" and
  the app shows the question with the options; the user signs or taps `yes` / `no` / `wait`; the
  answer is injected (the existing Bolna event-injection channel, ~0.8 s). No answer within ~10 s
  → the unattended behaviour. The agent does the greeting, spelling and small talk; the user acts
  only at the moments that are theirs.

The existing verbatim **live mode** (every sentence composed from signs and approved) stays as the
third option for personal calls.

**Why.** It removes real-time turn-taking pressure (one missed sign no longer stalls a receptionist),
needs only 2–3 content signs per call, fits service calls (clinic, visa, passport, restaurant), and
is what Bolna agents are built for: ~1 day on top of the existing backend (call placement, allowlist,
status webhook already exist). The attended variant keeps the live "sign → voice" moment for the
pitch, using recognition where it is most reliable (`yes` 0.91, `no` 0.64, `please` 0.95 first try).

**Safety that must carry over.** One explicit approval of the brief before dialling; the agent
discloses it is calling on behalf of a Deaf user; it may only pursue the brief and must not commit
outside it; transcript shown next to the summary (summaries can hallucinate, transcripts don't);
allowlisted consenting recipients only; a real call still needs the founder's go-ahead and a cost
heads-up (PLAN §10).

**Build (Ansuman, ~1 day):** `POST /briefs` (chips + profile → brief text, Groq-drafted, validator-
checked, shown for approval) → `POST /calls` with Bolna agent variables `{brief, user_name, …}` and
a prompt that forbids out-of-brief commitments → webhook handler stores transcript + summary →
`GET /calls/{id}/notes` → iOS "Notes" screen. Attended mode adds an "ask the user" node in the graph
agent that waits for an injected `answer` event with a 10 s timeout. Test with the fake Bolna first,
one real call to a teammate after approval.

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
