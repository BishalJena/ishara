# Voice experiment record

**Status: Not yet run.** No V4 spike call has been placed. Every "Executed" line below
is empty until a run is recorded; until then only the documented behaviour applies.
Pre-flight on 28 Oct (no call): Heroku now runs `main` with the D9 routes (release v9),
the live Bolna agent matches `agent.json` with the call summary on and speech before the
welcome message ignored, and the free smoke tests pass; see
[Deployed state before the first call](#deployed-state-before-the-first-call) and the
[go-live check](../status/2026-10-28-live.md).
This file is the authoritative summary of Path B voice measurements (task V4,
[Gate 1](../../PLAN.md#7-gates-go--no-go), testing layer 3 in
[PLAN.md §8](../../PLAN.md#8-testing-plan)). [Plan](../../PLAN.md) ·
[Workflow edge cases](../WORKFLOW.md) · [Claim ledger](../CLAIM-LEDGER.md) ·
[Recognition record](recognition.md)

## How runs are recorded

```sh
cd backend
uv run python -m scripts.voice_spike --base-url https://<app>.herokuapp.com \
    --contact clinic --confirm-cost            # all nine checks, end_call last
uv run python -m scripts.fake_app --base-url https://<app>.herokuapp.com \
    script --contact clinic --confirm-cost     # PLAN §1 script with a latency table (A3)
```

Both place a **real, paid** call (Bolna about ₹5.5/min plus telephony; a V4 spike is
about ₹20–30) to an allowlisted, consenting teammate with synthetic details, and need
explicit founder approval first. The runner appends a dated section under
[Runs](#runs) after the call has ended.

What the numbers mean:

- **SEND → spoken** is measured by the tool from sending `approve` to receiving
  `spoken {turn_id}`, which the backend emits when its custom-LLM stream to Bolna
  finishes. It is **not** first audio on the phone; PLAN §6 asks for SEND → first
  audio, which needs a stopwatch or a recording of the teammate's side.
- **Verdicts** (yes / no / skipped) and notes are the tester's observations of what
  the teammate heard.
- Results hold timings, counts and observations only. The writer removes call ids,
  turn ids and anything that looks like a phone number.

## Checks

Documented = what Bolna's docs or our design claim. Executed = what a recorded run
showed. Keep them separate.

### 1. Agent stays quiet while the teammate talks

- **Documented:** our custom LLM replies with nothing on the `listen` node, so the
  agent should stay silent ([PLAN §3](../../PLAN.md#3-architecture)); whether a graph
  agent can use a custom LLM at all is undocumented ([B23](../CLAIM-LEDGER.md)).
- **Measured by the runner:** captions, `spoken` events and `speaking` statuses inside
  the talking window.
- **Executed:** not yet run.

### 2. A `user_reply` event speaks the exact text

- **Documented:** event properties are substituted into the node prompt
  ([B18](../CLAIM-LEDGER.md)). **Contradicted live (28 Oct):** they are not, so the
  custom LLM now speaks the call's approved in-flight turn, not text from the prompt.
- **Measured by the runner:** outcome and SEND → spoken for a fixed test sentence.
- **Executed:** not yet run.

### 3. Holding line after silence

- **Documented:** `repeat_after_silence_seconds` on the waiting node can play
  "One moment please, I'm signing my reply." ([B22](../CLAIM-LEDGER.md)); silence
  hang-up and user-online detection must be off.
- **Measured by the runner:** captions and `spoken` events during the silence (the
  `[silence]` marker must not appear as a caption).
- **Executed:** not yet run.

### 4. Captions arrive at the backend

- **Documented:** the receptionist's words reach us only through Bolna's custom-LLM
  requests ([PLAN §3](../../PLAN.md#3-architecture)); status webhooks do not stream
  partial captions ([B11](../CLAIM-LEDGER.md)).
- **Measured by the runner:** caption count and time from the tester pressing Enter
  (teammate finished speaking) to the first caption.
- **Executed:** not yet run.

### 5. Sending the same `turn_id` twice speaks only once

- **Documented:** our design makes approvals single use per `turn_id`
  ([PLAN §4](../../PLAN.md#4-the-turn-when-signing-becomes-words)); enforced by the
  backend, not by Bolna.
- **Measured by the runner:** two identical `approve` messages; `spoken` count for that
  turn, `not_delivered` count and error codes.
- **Executed:** not yet run.

### 6. STOP: can unspoken or in-progress speech be cancelled?

- **Documented:** events never interrupt active speech and no utterance interrupt API
  was found ([B19](../CLAIM-LEDGER.md)); STOP in Path B may only cancel unspoken replies.
- **Measured by the runner:** outcome after STOP and the status sequence.
- **Executed:** not yet run.

### 7. An `end_call` event ends the call

- **Documented:** the `end_call` event moves to a static goodbye node that ends the
  call ([PLAN §3](../../PLAN.md#3-architecture)).
- **Measured by the runner:** time from `end` to `status ended`. Always run last.
- **Executed:** not yet run.

### 8. SEND while the teammate is still talking (B24)

- **Documented:** if the callee is mid-utterance when the event lands, the node
  transitions but the agent does not speak ([B24](../CLAIM-LEDGER.md)); the app must
  then show "not delivered, tap SEND again" and never resend on its own.
- **Measured by the runner:** outcome (spoken / not delivered / no confirmation) and
  SEND → spoken for a sentence sent a few seconds into the teammate's talking.
- **Executed:** not yet run.

### 9. Talk-over with "wait" (B25)

- **Documented:** speech above the interruption word count stops the agent and the
  stopwords "Stop", "Wait", "Hold on" always pause it ([B25](../CLAIM-LEDGER.md)); the
  `speak` node should use "words to interrupt" = 0.
- **Measured by the runner:** outcome and SEND → spoken for a long sentence.
- **Executed:** not yet run.

## Timings summary

Fill in from the runs below once at least one run exists.

| Measurement | Runs | Median | Range | Notes |
|---|---|---|---|---|
| SEND → spoken (tool, check 2) | 0 | — | — | not yet run |
| SEND → first audio (stopwatch) | 0 | — | — | not yet run |
| Teammate stops → caption (check 4) | 0 | — | — | not yet run |
| Chips → draft (fake app script) | 0 | — | — | not yet run |
| `end` → status ended (check 7) | 0 | — | — | not yet run |

## Gate 1 verdict

Not decided: no run yet. Gate 1 passes on exact text spoken, no double speech, a quiet
agent otherwise and captions reaching the backend
([PLAN §7](../../PLAN.md#7-gates-go--no-go)).

## Deployed state before the first call

Recorded on 28 Oct after the deploy go; **no call placed**. Details in the
[go-live check §5](../status/2026-10-28-live.md#5-gate-1-deploy-results-28-oct).

| What | State |
|---|---|
| Backend | Heroku release v9, Basic dyno; deployed tree equals `main`'s `backend/` (commit `878f71e`) |
| Bolna agent | Every payload field matches the live agent, including `call_summary_enabled: true` and `discard_pre_welcome_utterance: true`; agent-level interrupt threshold still 1 word |
| Free smoke tests | 7/7 pass: `/health`, `POST /briefs` with and without a token, OpenAPI routes, the `[silence]` holding line with the right and a wrong custom-LLM token |

## Runs

No runs yet. `scripts/voice_spike.py` appends one dated section per run below.
