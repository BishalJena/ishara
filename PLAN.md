# Ishara demo build plan

Updated **23 October 2026**. This file owns the active tasks, decisions and
acceptance criteria. Submission deadline: **Saturday 31 October 2026**.

**Visual version:** [architecture board](docs/architecture/README.md)
(`docs/architecture/ishara-board.excalidraw`). If the board and this plan disagree,
this plan wins; update both together.

Earlier plans live in the [archive](docs/archive/README.md). Measured ML results live
in the [experiment record](docs/experiments/recognition.md).

---

## 1. What we are building

A **demo-ready** iPhone app, not a full product for Deaf users. One signer, about
**12 signs** and **one rehearsed clinic call** that the team can present flawlessly.

```
Signer signs ─▶ iPhone recognises each sign ─▶ word chips ─▶ draft sentence
   ▲                                                            │ user taps SEND
   │ reads captions                                             ▼
Receptionist's words ◀── Bolna (Deepgram) ◀── phone call ◀── Bolna speaks (Sarvam voice)
```

### The demo story (the script we rehearse)

| Turn | Who | What happens |
|---|---|---|
| 0 | Bolna | Opens with a fixed disclosure: *"Hello, I'm calling for a Deaf caller who is using Ishara, a sign-language app. Their replies may take a few seconds."* |
| 1 | User | Signs **hello · doctor · tomorrow** → *"Hello, I'd like a doctor's appointment tomorrow."* → SEND |
| 2 | Receptionist | *"We have 4 pm tomorrow. Does that work?"* (appears as a caption) |
| 3 | User | Signs **no · morning** → *"No, sorry, 4 pm doesn't work. Is there anything tomorrow morning?"* → SEND |
| 3b | User | One planned wrong chip, removed with ✕ before SEND. This shows the safety design working |
| 4 | Receptionist | *"Yes, 10:30 tomorrow morning."* |
| 5 | User | Signs **yes · thankyou** → *"Yes, 10:30 tomorrow morning works. Thank you."* → SEND |
| 6 | User | Taps **End** → Bolna says goodbye and hangs up |

The receptionist role is played by a **consenting teammate** on their own phone,
with synthetic details. The call purpose ("doctor's appointment") is chosen on
the Home screen, not signed.

---

## 2. Decisions

Agreed on 23 October 2026. Raise any change explicitly; don't switch silently.

| # | Topic | Decision | Why |
|---|---|---|---|
| D1 | Who carries the call | **Option C.** Build **Path B** first: Bolna places the call through its default number. **Path A** (user's own number + Apple call-audio injection) is a Thursday bonus | B is testable before a device is available, gives the app real captions and uses Bolna centrally. A keeps the native-call story if it works |
| D2 | Voice (TTS) | **Sarvam Bulbul** (v4 Flash, English-India voice). Cartesia Sonic is the backup | Sponsor, inside Bolna's flat rate, Indian voice |
| D3 | Call language | **English (India)** only. Hindi is "next" | Lowest effort |
| D4 | Chips → sentence | **Cerebras LLM** drafts the sentence using the chips plus the live transcript, then a **validator** checks it. Fixed **templates** are the fallback | Fast, context-aware wording; templates catch meaning drift |
| D5 | Vocabulary | **12 signs** (see §5), one sign at a time with hands down between signs. Wait and Repeat are buttons | Enough for the script; small enough to record and rehearse |
| D6 | Where recognition runs | **On the iPhone**: MediaPipe Holistic for iOS plus SignCLIP converted to Core ML. The **Mac is the backup** | On-device is the pitch; the Mac pipeline already works |
| D7 | Backend hosting | Small Python backend on **Heroku** (**Basic dyno or higher**, never Eco) | Team has credits; Eco dynos sleep and Bolna would hear silence |

Already settled: native **SwiftUI** app, **SignCLIP** as the main recognizer
(SL-GCN as comparison), and **nothing is spoken unless the user taps SEND**.

**Buildathon rule** (official page, checked 23 Oct): any project qualifies if voice
is part of it; Bolna is not required by the rules. The team chose Bolna anyway (D1).

---

## 3. Architecture

### Where each piece runs

```
┌────────────── iPhone (SwiftUI app) ──────────────┐     ┌──── Heroku backend (Python) ────┐     ┌──── Bolna cloud ────┐
│ camera → MediaPipe Holistic → start/stop detector │     │ • call + turn state            │     │ graph agent          │
│ → SignCLIP (Core ML) → match vs your examples     │ WSS │ • composer: Cerebras + checks  │HTTPS│ Deepgram (hears)     │
│ → chips → draft (from backend) → SEND             │◀───▶│   + template fallback          │◀───▶│ Sarvam (speaks)      │
│ captions · call status · STOP / End               │     │ • custom-LLM endpoint for Bolna│     │ Plivo (phone line)   │
└───────────────────────────────────────────────────┘     │ • Bolna API client (calls,     │     └─────────┬────────────┘
                                                          │   events)                      │               │ PSTN
                                                          └────────────────────────────────┘     receptionist's phone
```

**API keys live only on the backend.** The phone holds a demo app token, never a
Bolna, Cerebras or Sarvam key.

### How Bolna is made to say exactly the approved text (Path B)

This uses documented Bolna features, but **the combination has not been run yet**.
Day 1 (task V4) proves it.

```
receptionist speaks ──▶ Bolna Deepgram ──▶ calls OUR /v1/chat/completions (custom LLM)
                                            ├─ we push the transcript to the app as a caption
                                            └─ we reply with nothing (agent stays quiet)

user taps SEND ──▶ backend: POST /v1/call/{run_id}/events  {event: "user_reply", properties: {reply_text, turn_id}}
               ──▶ Bolna moves to the "speak" node, whose prompt contains {{reply_text}}
               ──▶ Bolna calls OUR custom LLM ──▶ we stream reply_text back word for word
               ──▶ Sarvam speaks it into the call

long silence while the user signs ──▶ node's repeat_after_silence_seconds fires
               ──▶ our custom LLM returns "One moment please, I'm signing my reply."
```

Agent settings: **"hang up on user silence" OFF**, **"user online detection" OFF**,
a total call timeout of about 10 minutes, and an `end_call` event that moves to a static goodbye
node that ends the call.

### Path A difference (Thursday bonus)

The user dials from the normal Phone app and opens Ishara. On SEND, the backend asks
**Sarvam's TTS API directly** for a WAV clip, the app plays it, and Apple's
**Add Audio in Calls** injects it into the call. Apple documents that *any* app audio
is injected; this has not been run on a device yet. Captions come from iOS Live
Captions (the app can't read them), so the composer gets chips only and no transcript.

### Components and repo layout (new code)

| Component | Tech | Repo path | Status |
|---|---|---|---|
| iOS app | SwiftUI, AVFoundation, MediaPipeTasksVision, Core ML | `ios/Ishara/` | new |
| Recognition core (on device) | Swift detector + matcher; SignCLIP `.mlpackage` | `ios/Ishara/Recognition/` | new |
| Core ML conversion + parity | Python, coremltools | `ml/coreml/` | new |
| Mac recognition (backup) | existing Python (MediaPipe 0.10.21, SignCLIP) | `spikes/recognition/` | exists; extend vocabulary |
| Backend | Python 3.11, FastAPI, httpx, pytest | `backend/` | new |
| Bolna agent config | graph agent JSON | `backend/bolna/agent.json` | new |
| Composer | Cerebras client + validator + templates | `backend/app/composer.py` | new (templates ported from `spikes/recognition/sentence.py`) |
| Device harness (AAC test) | Apple sample, adapted | `spikes/call_flow/ios/` | exists |

### Interfaces (contracts to build against)

**App ↔ backend:** REST plus one WebSocket per call, authenticated with `APP_TOKEN`.

| Direction | Message | Meaning |
|---|---|---|
| app → backend | `POST /calls {contact_id, purpose}` | Start a Path B call. The backend only dials numbers on its allowlist |
| app → backend (WS) | `chips {turn_id, chips[]}` | Chips changed; recompose the draft |
| app → backend (WS) | `approve {turn_id, text}` | User tapped SEND with exactly this text. **Single use** |
| app → backend (WS) | `stop` / `end` | Cancel unspoken output / end the call |
| backend → app (WS) | `status {state}` | dialing · ringing · in_call · speaking · ended · error |
| backend → app (WS) | `caption {text, at}` | The receptionist's words (Path B only) |
| backend → app (WS) | `draft {turn_id, text, source: llm\|template}` | Composer result for the latest chips |
| backend → app (WS) | `spoken {turn_id}` | Bolna has spoken that reply |

**Backend ↔ Bolna:** `POST /call`, `POST /v1/call/{run_id}/events`, and our
`POST /v1/chat/completions` (custom LLM, OpenAI streaming format, bearer
`CUSTOM_LLM_TOKEN`, must be public HTTPS).

**Environment variables** (names only; values stay in Heroku config / local `.env`):
`APP_TOKEN`, `BOLNA_API_KEY`, `BOLNA_AGENT_ID`, `CUSTOM_LLM_TOKEN`,
`CEREBRAS_API_KEY`, `CEREBRAS_MODEL`, `SARVAM_API_KEY` (Path A only),
`ALLOWED_RECIPIENTS` (consenting test numbers only).

---

## 4. The turn: when signing becomes words

1. **Per sign (automatic).** Hands leave rest → start the clip. Hands are back at rest
   for about 0.4 s → end the clip → SignCLIP → match. If it's close enough, a chip appears;
   if not, a **[?]** chip appears and is never spoken. The target is about 0.5 s from the hands
   dropping to the chip appearing.
2. **Draft (automatic).** Every chip change sends `chips` to the backend. Cerebras
   drafts a sentence from the chips, the last receptionist caption and the call purpose.
   The **validator** rejects drafts that miss a chip's meaning, add a day, time, number
   or name that neither the user signed nor the receptionist said, or run past 25 words.
   A rejected draft, or no reply within 1.5 s, falls back to the template sentence.
3. **Message (the user decides).** The user taps **SEND**. The app never guesses that
   the message is finished. An approval is single use, tied to its `turn_id`, and
   wiped by Clear, a new turn or the end of the call.

Pauses cost nothing: hands at rest means nothing happens.

---

## 5. Vocabulary (12 signs)

| Sign | Used in script | Public reference video |
|---|---|---|
| hello | ✅ | INCLUDE |
| thankyou | ✅ | ISLRTC dictionary |
| yes | ✅ | ISLRTC dictionary (uses head movement too) |
| no | ✅ | ISLRTC dictionary (uses head movement too) |
| sorry | spare | ISLRTC dictionary |
| doctor | ✅ | INCLUDE |
| today | spare | INCLUDE |
| tomorrow | ✅ | INCLUDE |
| morning | ✅ | INCLUDE |
| afternoon | spare | INCLUDE |
| evening | spare | INCLUDE |
| time | spare | INCLUDE |

Reference videos are for **learning and checking** each sign. Recognition matches
against **your own recordings**. Dataset links: [research links](docs/research/links.md)
(INCLUDE, bridgeconn and silentone0725 ISLRTC dictionaries).

**Recording budget** (same signer who presents the demo, face and both hands in frame):

| Session | Per sign | Negatives (idle, transition, incomplete, unsupported) | Total clips |
|---|---|---|---|
| Enrollment | 3–5 | — | 36–60 |
| Calibration | 5 | 20 | 80 |
| Final test | 10 | 50 | 170 |

Each session must be a **separate recording session**. Clips are never reused
across sessions.

---

## 6. Schedule and todos

Owners: **[You]** = founder, **[Mate]** = teammate with the iPhone, **[Build]** =
engineering work in this repo. Each task says what "done" means, so it can be
picked up without earlier context.

### Fri 23 Oct: set up

- [ ] **H1 [You]** Create or confirm accounts and put the keys in the local `.env` (never in Git):
  Bolna API key with credits, Cerebras API key ($5 trial needs a payment card),
  Heroku app with a **Basic** dyno, and an Apple developer team in Xcode.
  *Done:* the backend's config check (V1) reports every key present.
- [ ] **H2 [You]** Give the consenting receptionist-teammate's number for `ALLOWED_RECIPIENTS`
  (it goes only in Heroku config / `.env`, never in the repo).
- [ ] **H3 [You]** Start learning the 12 signs from the reference videos (§5).
- [x] **P0 [Build]** Plan, decisions, board and doc fixes (this branch).
- [ ] **R0 [Build]** Extend the recognition tools from 5 to the 12 signs:
  `VOCABULARY` in `spikes/recognition/recognition_data.py`, plus tests.
  *Done:* `pilot_capture.py capture --concept morning` is accepted; tests pass.
- [ ] **V1 [Build]** Backend skeleton in `backend/`: FastAPI app, config loading from env,
  `/health`, pytest, `Procfile`, deployed to the Heroku Basic dyno.
  *Done:* `/health` is green on Heroku; tests pass locally.
- [ ] **V2 [Build]** Custom-LLM endpoint `/v1/chat/completions` that **logs the request
  shapes** Bolna sends (conversation, routing, end-of-call, voicemail) with secrets
  redacted, and streams an empty reply. *Done:* registered in Bolna as a custom model.

### Sat 24 Oct: day-1 Bolna test → Gate 1

- [ ] **V3 [Build]** `backend/bolna/agent.json`: graph agent with a disclosure welcome, a `listen`
  node (silence repeat about 15 s), a `speak` node (`{{reply_text}}`), and a static goodbye with
  `end_call`. Sarvam voice, Deepgram nova-3 en-IN, silence hangup and online check
  off. Create it via the API. *Done:* the agent exists and its id is saved in `BOLNA_AGENT_ID`.
- [ ] **V4 [Build + Mate]** Spike call to the teammate's phone (cost about ₹20–30, heads-up first):
  1. The agent stays quiet while the teammate talks.
  2. A `user_reply` event makes it speak the **exact** text.
  3. "One moment please" plays after silence.
  4. Captions arrive at the backend.
  5. Sending the same `turn_id` twice speaks only once.
  6. STOP: can unspoken or in-progress speech be cancelled?
  7. An `end_call` event ends the call.

  Record times from SEND to first audio. *Done:* results written in `docs/experiments/voice.md`.
- [ ] **G1 Gate 1** (see §7).
- [ ] **R1 [You]** Enrollment session: 3–5 takes × 12 signs with `pilot_capture.py`, then
  review the overlays and `verify` each label against its reference video.
- [ ] **R2 [Build]** Start/stop detector on the Mac (rest calibration, hands-up start,
  0.4 s rest end, minimum and maximum length) over live webcam and saved clips.
  *Done:* it cuts the enrollment takes correctly; unit tests cover the boundaries.
- [ ] **P1 [Build]** Convert the SignCLIP video encoder to Core ML (`ml/coreml/`), FP16, with
  padding to ≤256 frames. *Done:* the `.mlpackage` gives the same embeddings as PyTorch (cosine ≥ 0.999)
  on the saved clips.

### Sun 25 Oct: composer, calibration

- [ ] **V5 [Build]** Composer: templates for the 12 signs plus purpose, a Cerebras prompt, the validator,
  a 1.5 s timeout and the fallback. *Done:* a fixture test for every script turn (§1), and
  validator tests for invented times, a missing "no" and an over-long draft.
- [ ] **R3 [You]** Calibration session: 5 × 12 signs plus 20 negatives.
- [ ] **R2b [Build]** Set the "close enough" cut-off on the calibration session only, then freeze it.
- [ ] **A1 [Build]** Xcode project `ios/Ishara/` with the 4 screens from the board (Home, Get ready,
  Active call signing, Active call speaking) running on fake data in the simulator.

### Mon 26 Oct: final recognition test → Gate 2

- [ ] **R4 [You]** Final test session: 10 × 12 signs plus 50 negatives. **Evaluate once.**
- [ ] **G2 Gate 2** (see §7).
- [ ] **V6 [Build]** Call session layer: `POST /calls` with the allowlist, the WebSocket messages (§3),
  `turn_id` handling, single-use approval, stale-turn rejection, caption forwarding and
  WebSocket pings. *Done:* tests for double SEND, stale approval and an ended call.

### Tue 27 Oct: on-device pipeline → Gate 3

- [ ] **P2 [Build]** MediaPipe Holistic (iOS) feeding the Swift detector and matcher, using the
  frozen cut-off and your enrollment references bundled in the app.
- [ ] **P3 [Build]** Parity: run the same saved videos through the simulator pipeline and through the Mac.
  *Done:* both give the same accepted label (or "?") on every calibration clip.
- [ ] **G3 Gate 3** (see §7).
- [ ] **A2 [Build]** Wire the app to the backend: start call, chips → draft, SEND, captions,
  status, STOP, End. Uses the replay-video recognizer in the simulator.

### Wed 28 Oct: full flow in the simulator

- [ ] **A3 [Build]** Full script with a **real Bolna call** to the teammate, the app in the simulator
  replaying recorded sign videos. *Done:* the whole §1 script works twice in a row.
- [ ] **A4 [Build]** Mac fallback: the Mac webcam recognizer posts chips to the same backend
  WebSocket, so the demo works even without the on-device recognizer.
- [ ] **A5 [Build]** Path A mode (bonus): backend `/tts` (Sarvam) → WAV → app plays it
  with the injection mode on. Needs `SARVAM_API_KEY`.

### Thu 29 Oct: real iPhone → Gate 4

- [ ] **T1 [Mate]** Install on the iPhone (Xcode, dev team). Record the iOS version, enable
  **Add Audio in Calls**, and grant camera and injection permissions.
- [ ] **T2 [Mate + You]** Path B full script live on the phone camera, plus the edge-case run:
  long pause, fidgeting, wrong chip, out of frame, double SEND, receptionist
  interrupting, network off, End.
- [ ] **T3 [Mate]** Path A bonus: own-number call, play a Sarvam clip, recipient repeats what they
  heard; camera and Live Captions on at the same time.
- [ ] **G4 Gate 4** (see §7).

### Fri 30 Oct: polish and rehearse

- [ ] **D1 [All]** Fix Thursday's failures only. No new features.
- [ ] **D2 [You + Mate]** Rehearse the script 3 times and **record a backup video**.
- [ ] **D3 [You]** Write the submission text (what it does, honest limits §9, Bolna and partner use).

### Sat 31 Oct: submit

- [ ] **D4 [You]** Submit before the deadline. **Confirm the exact cutoff time and timezone**
  on the buildathon page or Slack beforehand.

---

## 7. Gates (go / no-go)

| Gate | When | Pass | If it fails |
|---|---|---|---|
| **G1** Voice | Sat 24 | Exact text spoken on the call; no double speech; agent stays quiet otherwise; captions reach the backend | Fallback 1: the speak node uses a built-in LLM with a "repeat exactly" prompt and the backend checks the transcript. Fallback 2: Path A becomes the main path |
| **G2** Recognition | Mon 26 | Final test: **≥ 9/10 per sign**, **0 wrong accepted signs**, **0 accepts on the 50 negatives**, **< 2 s** from the sign ending to the chip, measured live | Drop or replace the signs that get confused (choose more distinct ones), add quick-reply taps, recollect a new final session (the old one becomes development data) |
| **G3** On-device | Tue 27 | The simulator pipeline matches the Mac on every calibration clip | Demo recognition on the Mac (A4) and pitch "designed for on-device" |
| **G4** Real call | Thu 29 | The full script works live twice on the iPhone; the recipient hears exactly the approved sentences | Friday becomes a fix day; the Mac fallback and the backup video are the safety net |

---

## 8. Testing plan

| Layer | What | When | Pass looks like |
|---|---|---|---|
| 1. Unit | detector boundaries, matcher cut-off, templates, validator, single-use approval, stale turns, allowlist | every commit | `pytest` (backend) and `python -m unittest` (spikes) green; XCTest for the Swift detector and matcher |
| 2. Recognition | separate calibration and final sessions | Sun–Mon | G2 numbers, with counts and denominators written down |
| 3. Voice | exact text, SEND → first audio time, double SEND, STOP, Bolna down → silent | Sat–Sun | G1, plus timings recorded in `docs/experiments/voice.md` |
| 4. Simulator | saved videos through the iOS pipeline; app flow with a real call | Tue–Wed | G3 and A3 |
| 5. Real iPhone | camera, voice and captions together; mute, app switch, End, next call clean | Thu | G4 |
| 6. Demo | full script × 3, backup video | Fri | a clean recording |

Mutation-minded tests: every safety rule (single-use approval, no invented times,
"?" never spoken, allowlist) needs a test that **fails if the rule is removed**.

---

## 9. Honest limits (say these in the pitch)

- About 12 signs, tuned to the person who recorded them; one sign at a time, with hands down
  between signs. This is not general ISL translation or continuous signing.
- Path B calls come from a Bolna number, not the user's own number. Path A keeps the
  user's number but relies on iOS Live Captions, which the app cannot read.
- The LLM can reword, but it cannot add facts; the user approves every sentence.
- No Deaf participant has validated the design.

---

## 10. Safety and evidence rules

- Calls go only to numbers in `ALLOWED_RECIPIENTS`, i.e. consenting teammates, with synthetic
  appointment details. No unexpected or third-party calls.
- Give a cost heads-up before paid runs (Bolna is about ₹5.5/min plus telephony; Cerebras is billed by tokens).
- No keys, phone numbers, account IDs or raw account responses in Git, issues or PRs.
- Record what actually ran (counts, timings, configs) separately from what docs claim.
