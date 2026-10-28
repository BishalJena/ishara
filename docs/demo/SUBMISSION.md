# Submission text (draft for task D3)

Draft for the founder, written 28 October 2026. Edit freely, but keep every claim tied to its
source in the right-hand column, and update the **Pending** list on the day: anything
still pending must stay marked as not done. Sources: [claim ledger](../CLAIM-LEDGER.md),
[ASL model probe](../experiments/asl-model-probe.md), [simulator parity evidence](../experiments/evidence/asl-model-probe/parity-simulator-lifeprint.json),
[video pipeline evaluation](../experiments/video-pipeline-eval.md), [voice record](../experiments/voice.md),
[plan](../../PLAN.md), [handoff](../handoffs/2026-10-26-ready-made-asl-recognizer.md).
Demo flow: [SCRIPT.md](SCRIPT.md).

---

## Ishara: phone calls for people who sign

**One line.** Ishara is an iPhone app that lets a signer make a voice phone call: sign what
you need, approve it, and a voice agent says it on the call, while you read the other side
as captions. Nothing is said on the call without your approval.

### What it does

- **Live mode.** You sign one word at a time; each recognised sign becomes a word chip;
  Ishara drafts a short sentence from the chips and the last thing the receptionist said;
  **nothing is spoken until you tap SEND**. The receptionist's words come back as captions.
- **Call for me.** You sign what you need (for example TOMORROW), check a short
  brief, and approve it once. The voice agent then makes the call and pursues only that
  brief. When the receptionist offers a time, the agent says "One moment, please." and asks
  you on screen; you sign or tap yes, no or wait, and see the exact sentence each choice will
  say. If you don't answer within 10 seconds, or you chose not to stay on, the agent says it
  will call back instead of deciding for you. Afterwards you get call notes: the outcome, what
  was offered, what you answered, and the transcript.
- Every call opens with a disclosure: "Hello, I'm calling for a Deaf caller who is using
  Ishara, a sign-language app. Their replies may take a few seconds."
- **Calls are placed from a Bolna phone number, not the user's own number.** Before every
  call the app says: "Calls are placed from Ishara's calling number, not your own number. The
  receptionist hears an automated voice reading what you approve." (Ishara's calling number
  is Bolna's default number.)

### How it works, and how Bolna and the partners are used

| Part | What we use | How |
|---|---|---|
| Sign recognition, on the phone | The Kaggle ASL Signs 1st-place model (MIT code, 250 signs, trained on a CC-BY 4.0 corpus of about 94k clips from 21 Deaf signers), run with LiteRT; MediaPipe Holistic for landmarks | Used **as is**: no training, no fine-tuning, no own recordings. Open-set rule: full 250-way softmax over every sign; only the eight rehearsed words can become a chip, at p ≥ 0.65 (per-word 0.45–0.6) with margin ≥ 0.3; "Did you mean …?" from 0.35 up to that cut-off, which counts only when tapped; any other sign, however confident, is `?`, never spoken. Cut-offs are provisional until the iPhone clips |
| **Bolna** | Graph voice agent, outbound call API, event injection, custom LLM, status webhook with call summary | Bolna places the call from its default number. Our backend is registered as the agent's custom LLM, so Bolna asks our backend what to say; an approved sentence goes in as an event and is spoken word for word. Fixed welcome (the disclosure) and goodbye are Bolna static lines. Bolna's own call summary is shown in the notes, marked as possibly wrong |
| **Sarvam** | Bulbul v4 Flash voice (English, India), inside Bolna | The voice the receptionist hears. Also called directly for the own-number bonus mode (Path A), which is not part of the demo |
| **Deepgram** | nova-3 speech-to-text, inside Bolna | Turns the receptionist's speech into the captions and into what the agent responds to |
| **Plivo** | Telephony provider of the Bolna agent | The phone line |
| **Groq** | `openai/gpt-oss-120b` | Rewords chips into a natural sentence, and phrases the Call-for-me agent's replies. A validator rejects any draft that drops a signed meaning or adds a day, time, number, name or agreement the user didn't sign; fixed templates are the fallback (also when Groq takes longer than 1.5 s). Every Call-for-me agent line passes `check_line`, with rule-based lines as the fallback |
| Backend | Python, FastAPI, on Heroku (Basic dyno, EU region) | Call and turn state, single-use approvals tied to a turn id, the allowlist of numbers, captions to the app, the custom-LLM endpoint for Bolna. API keys stay on the backend, never in the app |

### What we measured (and how much)

| Claim | Result | Source |
|---|---|---|
| The model, untouched, recognises ASL signs from a signer it never saw | 6 of 11 Lifeprint ASL clips right at p 0.70–0.94; misses `morning` and `sick` | Probe record, ledger R24 (one reference signer, Mac) |
| ... and the presenter's signs | yes / no / now / please right on the first attempt (0.91 / 0.64 / 0.93 / 0.95); `tomorrow` top-1 on 17 of about 21 attempts at only 0.30–0.66 | Probe record, R24 (laptop webcam, labels inferred, no iPhone) |
| Wrong words are kept out | 0 wrong auto-accepts at p ≥ 0.6 over 55 presenter cuts and 79 ISL clips | Probe record, R24 |
| ... on public ASL clips, both the Mac and the app path | 142 public dictionary clips (110 signs from 6–10 sources per word, 32 negatives), landscape and portrait: 0 wrong chips on all four runs with chips limited to the rehearsed words and the provisional cut-offs (1–2 per run before, all `can`, `hungry`, `time`); 50–60 % of signs chip. The cut-offs were fitted on the same clips, so this is optimistic. Per-word gate still fails for `yes`, `hello` and `morning` | Probe record, Run 5 |
| Speed | 4 ms per sign on a Mac CPU; 0.43–0.50 s from hands at rest to chip on the Mac webcam; about 15 ms per 1.5 s clip with LiteRT in the iOS simulator | Probe record; R21 |
| The phone path matches the Mac | 18 Lifeprint clips through the app's own path in the simulator: same chip on all 9 clips the Mac is confident about, decisions agree on 17 of 18 | Parity evidence, PLAN P3 |
| The composer | On ground-truth chips, 9 of 12 drafts came from Groq and passed the validator, the other 3 fell back to templates; script turns in 0.17–0.22 s | Video pipeline evaluation |
| Call for me, end to end, offline | Brief → disclosure → opening → offer → "One moment, please." → yes → spoken → notes "Booked", through the real backend code with a scripted receptionist and the iOS screens | Handoff "Built on 27 Oct"; re-run 28 Oct for the [script](SCRIPT.md) |
| Real calls | Real Bolna calls for live mode and Call for me (attended and unattended) passed on 28 Oct. The unattended call's notes said "unclear" instead of "callback"; a fix is in progress | Founder's live runs, 28 Oct |

ISL overlap was measured, not assumed: the ASL model reads ISL `thankyou` 7 of 8 times and
the ISL wave `hello` 7 of 9, and nothing else we tried (ledger R23). We kept the demo pure ASL.

### Not measured yet (pending on 28 Oct)

Update this list on submission day; anything not done stays here.

- **Measurements on the real calls.** The 28 Oct calls passed, but SEND → first audio time
  and the receptionist talking over a reply (ledger B24) are not measured yet.
- **iPhone.** Nothing has run on the iPhone yet: install, live camera, frame rate, chip latency.
- **The phone-clip recognition check** (8 words × 5 attempts plus negatives, gate ≥ 6/10 per
  word, 0 wrong auto-accepts). Until then the thresholds are the provisional public-clip
  candidate.
- **MORNING.** The model learned a one-handed form; whether the presenter's MORNING chips is
  for the iPhone test. Until then it cannot become a chip (it can still be tapped).
- **Groq's wording in Call for me**, and Groq on the live-mode turns other than the ones above.
- **Any Deaf user.** No Deaf participant has tested Ishara.

### Honest limits

- **A published, signer-independent ASL model trained on public data from 21 Deaf signers;
  the presenter is hearing and learned the signs from Lifeprint; ISL is the goal and is
  blocked by data, which is the problem we want to solve; nothing is spoken on a call without
  the user's approval; no Deaf-user validation yet.**
- A small rehearsed vocabulary (hello, thankyou, yes, no, now, please, tomorrow; wait is a
  candidate; morning is pending the iPhone test), one sign at a time with hands down between
  signs. This is not general
  translation or continuous signing.
- Calls come from a Bolna number, not the user's own number. The own-number mode (Path A)
  keeps the user's number but relies on iOS Live Captions, which the app cannot read; it is a
  bonus and not in the demo.
- The LLM can reword, but it cannot add facts; the user approves every sentence, or every
  yes/no in Call for me.
- The demo call is with a consenting teammate playing the receptionist, with synthetic
  details. It is a rehearsal, not a validated natural conversation.

### What's next

- ISL: build consented, signer-diverse ISL data with Deaf partners; the open-set design carries
  over.
- Test with Deaf users first.
- Own-number calls, Hindi, a larger vocabulary.

### Credits

- ASL Signs corpus (CC-BY 4.0, Deaf Professional Arts Network and Georgia Tech) and the
  1st-place model by hoyso48 (MIT), weights from the `sign/kaggle-asl-signs-1st-place` mirror.
- MediaPipe (Google) and LiteRT / TensorFlow Lite C (Apache-2.0).
- Lifeprint / ASL University (Bill Vicars): the presenter learned the signs there; clips were
  used for local evaluation only and are not redistributed.
- INCLUDE (AI4Bharat) and the ISLRTC dictionary: used to measure the ISL overlap, with
  acknowledgement; not redistributed.
- Bolna, Sarvam, Deepgram, Plivo and Groq, as above.
