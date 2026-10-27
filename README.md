# Ishara

Ishara is a hackathon prototype that helps Deaf and nonspeaking people handle service calls
(a clinic, a visa or passport office, a restaurant) by signing instead of speaking. The iPhone
recognises signs on the device, the user approves what will be said, and a voice agent speaks
on the call. Two ways to use it:

- **Live call:** sign each reply; the app drafts a sentence, you tap **SEND**, and it is spoken
  into the call. The other person's words come back as captions.
- **Call for me:** sign what you need (for example TOMORROW · MORNING), read the brief built
  from exactly that, approve it once, and the agent makes the call. If you stay, it asks you
  yes / no / wait when a decision is yours; if you don't, it says it will call back. Either way
  you get notes and the full transcript afterwards.

**Phase: demo build** for the Bolna Symphony buildathon (submission 31 October 2026): one
rehearsed clinic call, a small rehearsed vocabulary, not a general sign-language translator.

## What it recognises, and what it doesn't

The demo uses **American Sign Language (ASL)** through a published, signer-independent model
(the [Kaggle ASL Signs](https://www.kaggle.com/competitions/asl-signs) 1st-place model, trained on
public data from 21 Deaf signers), used as is: no recordings of our own, no training. Of its
250 signs the app can phrase 34, and 8 are rehearsed for the demo (hello, thank you, yes, no,
now, please, tomorrow; wait and morning as candidates).

**Indian Sign Language is the goal** and is blocked by data: the public ISL sets have too few
examples per sign to recognise new signers safely ([what we measured](docs/experiments/asl-model-probe.md)).
Recognition abstains rather than guesses: an unsure sign shows as **[?]** or a "did you mean …?"
that counts only if tapped. No Deaf user has tested the app yet.

## How it works

![Architecture board](docs/architecture/ishara-board.png)

- **iPhone (SwiftUI):** camera → MediaPipe Holistic → sign detector → the ASL model via LiteRT
  → chip, "did you mean", or [?]. Screens: Home, Get ready, Call, Brief, Notes. No API keys on
  the phone.
- **Backend (FastAPI on Heroku):** call and turn state with single-use SEND approvals; the
  draft composer (Groq, with a validator that rejects invented days, times, numbers and names,
  and templates as fallback); briefs and the delegated agent's brain; Bolna's custom-LLM
  endpoint; call notes.
- **Bolna:** places the call from its number (Plivo), transcribes with Deepgram and speaks with
  a Sarvam voice. A bonus mode (Path A) plays the approved sentence into the user's own Phone
  call with Apple's Add Audio in Calls, without app captions.

The [architecture board](docs/architecture/README.md) has the full picture.

## Where the build is (27 October)

- Built and tested in the iOS simulator: both call modes, and the ASL model running inside the
  app. On the same 18 ASL test clips the app and the Mac reach the same decision on 17.
- "Call for me" runs end to end against the real backend code with a scripted receptionist.
- **Not yet:** clips from the iPhone's front camera, speed on the iPhone, and a real Bolna call.
  The confidence thresholds are provisional until the phone clips are in.

[PLAN.md](PLAN.md#6-schedule-and-todos) tracks every task and gate.

## Try it

```sh
scripts/verify.sh                         # every test suite; fetches the LiteRT library once
```

- **iOS app:** see [ios/README.md](ios/README.md) (three download scripts, then Xcode). It runs
  a scripted demo call with no backend by default; "CALL FOR ME" works the same way.
- **Backend:** [backend/README.md](backend/README.md); `uv run python -m scripts.local_demo`
  serves the whole call locally with a scripted receptionist, free, nothing dialled.
- **Mac webcam:** `scripts/sign_lab.sh --free --model asl` signs into a local call;
  add `-- --delegated --attended --name "Asha"` for Call for me.

Model files, recordings and credentials are not in Git; the runbooks say what each script fetches.

## Reference

- [Plan](PLAN.md): decisions, tasks and gates (the source of truth).
- [Workflow and edge cases](docs/WORKFLOW.md): what the user does and what the app does.
- [Architecture board](docs/architecture/README.md)
- [ASL model measurements](docs/experiments/asl-model-probe.md); earlier
  [ISL recognition experiments](docs/experiments/recognition.md).
- [Source claim ledger](docs/CLAIM-LEDGER.md): every external claim, dated and qualified.
- [Research index](docs/research/README.md) and [archive](docs/archive/README.md): how the
  project got here, including the personalised ISL approach it moved away from.
