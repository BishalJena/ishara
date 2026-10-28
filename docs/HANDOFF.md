# Teammate handoff

## Current state: 28 October 2026

**What works, on `main`:** the demo is pure ASL (D8): the public Kaggle ASL Signs model runs
inside the app and on the Mac, and only **hello, thankyou, yes, no, now, please, tomorrow,
wait** can become a chip (provisional cut-offs). Both call modes are built: **Live** (sign, check
the draft, tap SEND) and **Call for me** (D9: approve a brief once; the agent calls, asks you
YES / NO / WAIT or a time word when a decision is yours, or promises a callback). The backend is
on Heroku with one worker, and the Bolna agent matches `backend/bolna/agent.json`.

**What ran for real on 28 Oct:** real Bolna calls to the founder's verified phone. The first
ones failed five ways (trial account, Bolna not filling event properties, two web workers,
times in words, "unclear" notes), each fixed at its root; then Live mode and all three
Call-for-me flows passed, end to end from the simulator app with sign videos as the camera.
Details: [status, 28 Oct](status/2026-10-28.md) and the [voice record](experiments/voice.md#runs).

**What is left, in order** (the PLAN's [task list](../PLAN.md#6-schedule-and-todos) has the ticks):

1. **The iPhone test: [issue #72](https://github.com/BishalJena/ishara/issues/72).** Written
   for whoever holds the phone: install (about 45 min once), the signs on the live camera
   (including the one-handed MORNING, 10 tries), two real calls with the founder after a go,
   and a results comment. Gate 4 depends on it. Note: morning is not in the shipped chip
   vocabulary, so a MORNING attempt always shows `?` on screen; the model's top-3 for each sign
   is in the app's log (subsystem `ai.ishara.demo`, `asl chip|pick one|unsure … p= [top3]`), so
   read that, or film the attempts and score them on the Mac.
2. **Phone clips → final thresholds:** the 8 chip words × 5 plus negatives, through both paths,
   then freeze the bundle ([how](handoffs/2026-10-26-ready-made-asl-recognizer.md#the-phone-clips-the-one-measurement-still-missing)).
3. **Rehearse** the [demo script](demo/SCRIPT.md) three times, record a backup video, finalise
   the [submission text](demo/SUBMISSION.md).
4. Open issues worth a look before the demo: #91 (the WAIT line in notes), #96 (notes miss
   Bolna's summary), #86; the rest are listed in the [status](status/2026-10-28.md#6-known-issues-open).

**Calling number:** the app says calls come from "Ishara's calling number". That number is
provided by Bolna, not the user's own; the founder kept this wording (issue #51), and the
presenter, slides and submission say it is a Bolna number.

**Demo-only:** with no backend, the app plays a scripted fake call (`DemoScript.swift`,
`DelegatedDemo.swift`, `DemoFixtures.swift`) that still signs `doctor`, `afternoon` and
`morning`. That is scripted playback, not recognition; none of those words can chip from a real
sign now.

Start with the [handoff for D8/D9](handoffs/2026-10-26-ready-made-asl-recognizer.md) for how
recognition and Call for me work, and [docs/TESTING.md](TESTING.md) for every test command.

## History: the state on 24 October

The sections below are kept as they were on 24 October (SignCLIP, 12 ISL signs, no real
call yet). The current direction is above and in [PLAN.md](../PLAN.md).

Current state then: **24 October 2026**, branch `main` (PRs #5–#33 are merged).
This file owns the current capability and direction. Detailed measurements belong
in the [experiment record](experiments/recognition.md), active tasks in
[PLAN.md](../PLAN.md), and commands in the spike runbooks.

### What worked

- The Mac browser diagnostic runs real OpenHands SL-GCN predictions on saved clips,
  fixed sentence templates, exact editing and single-use approval.
- The separate SignCLIP experiment produces real local embeddings and compares
  clips with labeled ISL references. Its replay outputs deliberately abstain.
- Capture, landmark-overlay review, explicit label verification and
  session-separated calibration/evaluation tools are implemented.
- The speech track has an offline lifecycle mock, a non-telephony Bolna probe and
  an Apple audio/camera diagnostic harness. These are separate tools.

### Demo build progress (24 Oct, merged)

Everything below is on `main` with offline tests (`scripts/verify.sh`: backend 782
tests, recognition, call_flow, three Swift packages, iOS app under `xcodebuild test`).
[PLAN §6](../PLAN.md#6-schedule-and-todos) has the per-task status.

**What has run for real (23–24 Oct):** the backend is deployed to Heroku (EU, Basic
dyno) with `/health` green; the custom model is registered with Bolna and the Path B
graph agent exists (its id lives only in Heroku config and the local `.env`); a live
custom-LLM smoke returned the holding line for `[silence]`. Groq and Sarvam have been
called for lab drafts and oracle audio (a few rupees in total). **What has not:** no
Bolna call has been placed (V4), no sign of the presenting signer has been recorded
(R1/R3/R4), and nothing has run on an iPhone (P3/T1). The gates G1–G4 are all open.

| Area | What exists | PRs |
|---|---|---|
| Backend (`backend/`) | FastAPI app, Groq composer with validator and templates, Bolna custom-LLM endpoint, call sessions with single-use approvals, status webhook with its own secret, Path A `/tts`, Bolna agent builder and CLI, fake Bolna and end-to-end script tests, fake-app and V4 spike tools, Sign Lab backend | #6–#8, #10, #13–#17, #26, #30 |
| CI and deploy | `scripts/verify.sh`, GitHub Actions, Heroku scripts and `backend/HEROKU.md` | #15, #28 |
| iOS (`ios/`) | `ios/Ishara` app (live call and "Call for me" (D9) flows: Home, Get ready, Brief, call, Notes; fake and live call drivers, scripted and pipeline recognition with the ASL Signs model through LiteRT, D8) and local packages `ios/Packages/{RecognitionCore,CallSession,SignPipeline,SignPipelineMediaPipe,SignPipelineLiteRT}`; unit and UI tests pass in the simulator, including "Call for me" against the local demo backend | #18, #20, #22, #23, #27, #46 |
| Core ML (`ml/coreml/`) | SignCLIP encoder as FP16 Core ML; matches PyTorch on 47/47 clips with `.cpuAndGPU` on a Mac (the Neural Engine gives wrong embeddings, so the app refuses it) | #21 |
| Mac recognition | 12-sign vocabulary, calibration report and bundle export, start/stop detector, live webcam recognizer with top-3 display, Mac bridge into the backend call, guided 12-sign recording session and provisional try bundle | #9, #11, #12, #25, #29, #32 |
| Evaluation | Cross-signer run on 42 public clips through recognizer, composer and voice: right sign ranked first for 27/39, but 4 correct chips, 1 wrong, the rest `?` at the zero-wrong-accept cut-off; composer on true chips 9/12 fit, one validator gap (see plan task V5b) | #33 |

### Direction and blockers then

**SignCLIP is the leading representation for fresh-data evaluation.** Reference
matching improved the ranking of the saved intended-hello attempts, but those
recordings cover one intended meaning. Unknown-sign rejection remains unresolved,
and whole-clip extraction has not met the live response target.

The demo vocabulary is now **12 signs** (hello, thankyou, yes, no, sorry, doctor,
today, tomorrow, morning, afternoon, evening, time), for one seated signer and one
complete sign at a time; the capture and recording tools use it (plan task R0 done).
The older browser diagnostic also supports today and location.
Its recognizer is still SL-GCN; uncalibrated SignCLIP ranks are not connected to
composition or speech.

**Composer (decided 23 Oct):** a Groq LLM (`openai/gpt-oss-120b`; it replaced
Cerebras, which is not free) drafts the sentence from the chips plus the live call
transcript, a validator rejects missing meanings or invented
days, times, numbers and names, and the fixed templates are the fallback. The
earlier local Qwen experiment changed the meaning of a requested-day example, which
is why the validator and template fallback exist. No composer can repair an
incorrectly recognized concept; the user still edits and approves.

**Bolna speech is unproven.** The old hosted sample-speech route returned 403
and should not be retried. The chosen route (Path B) is a Bolna graph agent that
places the call, with our backend as its custom LLM; a graph event moves it to the
speak node and the backend streams the call's approved turn (events can't carry the
text: Bolna never puts their properties in a prompt, seen live 28 Oct); day-1 task V4
in the plan tests it. The endpoint is deployed, the custom
model and the graph agent are registered with Bolna, and the spike runner exists, but
no call has been placed. The iPhone harness has been
built, but physical call/camera/caption coexistence (Path A) has not been
demonstrated. An offline mock or Apple local voice does not establish Bolna
integration.

There is no end-to-end validated product, trained personalized model or Deaf
participant validation. See the [workflow](WORKFLOW.md) for the proposed composition.

## Start working

Clone the repository (all spike work is on `main`):

```sh
git clone git@github.com:BishalJena/ishara.git
cd ishara
```

Then follow the runbook for the relevant track:

- [iOS app](../ios/README.md): three download scripts, then Xcode; the iPhone steps are
  [issue #72](https://github.com/BishalJena/ishara/issues/72).
- [Backend](../backend/README.md) and [Heroku](../backend/HEROKU.md): `scripts.local_demo`
  serves a whole call locally for free.
- [Recognition](../spikes/recognition/README.md): environment setup, public clips,
  the ASL model on the Mac, the probe and summary tools.
- [Speech/device](../spikes/call_flow/README.md): offline tests, provider probe
  boundaries and the iPhone diagnostic.

The repository is private. Weights, recordings, credentials, generated evidence
and signing identities are excluded. Setup fetches public assets; a fresh clone
does not contain the private footage behind the recorded webcam results.
Mac/Python 3.11 is the tested ML setup; other platforms are unverified.

The immediate human input is the iPhone test in
[issue #72](https://github.com/BishalJena/ishara/issues/72) and the phone clips that freeze
the thresholds. No own recordings or training are needed (D8).

## Reading map

- [Research index](research/README.md): why these methods were selected and where
  the primary evidence lives.
- [Experiment record](experiments/recognition.md): actual results, regressions,
  timing, validation counts and reproducibility limits.
- [Source claim ledger](CLAIM-LEDGER.md): dated platform/provider claims.
- [Archive](archive/README.md): earlier proposals and completed task notebooks.

The product remains one seated administrative appointment conversation. On
23 October the team chose Option C: Bolna places the call first (Path B, disclosed
as coming from Ishara's calling number, a Bolna number, with real in-app captions from Bolna's transcriber),
and the user's own-number call with Apple call-audio injection (Path A) is a bonus.
In Path A, system captions are visible to the user but are not readable by Ishara.
See [PLAN.md](../PLAN.md#2-decisions).
