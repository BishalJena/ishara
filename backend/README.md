# Ishara backend

FastAPI service for Path B ([PLAN.md §3](../PLAN.md#3-architecture)): app sessions, the Groq
composer, Bolna's custom-LLM endpoint, and the "Call for me" mode (decision D9: briefs, the
delegated agent, call notes). Python 3.11, managed with `uv`.

```sh
cd backend
uv sync
uv run python -m app.config          # which env names are set (never prints values)
uv run pytest -q
uv run ruff format --check . && uv run ruff check .
uv run uvicorn app.main:app --reload # http://127.0.0.1:8000/health
```

Settings come from the environment or the repo-root `.env` (see `../.env.example`).

## Module map

| Module | Owns |
|---|---|
| `app/main.py` | `create_app(...)` (injectable, for tests), `build_app(settings)` (real wiring), the lazily built `app` that uvicorn serves, logging, `/health` |
| `app/config.py` | Settings from env / `.env`; `python -m app.config` lists missing names |
| `app/protocol.py` | App ↔ backend messages, the 34-sign vocabulary (12 template signs + 22 ASL glosses, D8), composer request/draft, D9 briefs, asks and notes |
| `app/markers.py` | Marker block in Bolna node prompts that ties custom-LLM requests to a call and turn; event, property and webhook path names |
| `app/ports.py` | `Composer`, `BolnaClient` (+ its `BolnaError`), `CallLedger` interfaces between modules |
| `app/auth.py` | `APP_TOKEN` and `CUSTOM_LLM_TOKEN` bearer checks |
| `app/calls.py` | Session layer I/O: `POST /calls` (live or delegated), `POST /briefs`, `GET /calls/{id}/notes`, app WebSocket (incl. asks and answers), Bolna status webhook, `CallLedger` (V6) |
| `app/delegate.py` | D9: the brief built only from chips and profile, the agent's brain (Groq with a rule brain fallback), the line checker that rejects invented facts, and the notes built from the transcript |
| `app/sessions.py` | Pure turn and approval rules: stale turns, single-use SEND, single claim |
| `app/contacts.py` | `ALLOWED_RECIPIENTS` parsing (`contact_id=+E164`) |
| `app/bolna_status.py` | Bolna execution statuses → call states |
| `app/custom_llm.py` | `POST /v1/chat/completions` for Bolna (V2): request kinds, captions, verbatim replies |
| `app/openai_chat.py` | Lenient OpenAI chat request models and SSE / completion builders |
| `app/utterances.py` | Which receptionist utterances in Bolna's resent history are new |
| `app/shape_log.py` | Redacted request-shape log lines (also to `CUSTOM_LLM_SHAPE_LOG`, keep under `artifacts/`) |
| `app/composer.py` | `build_composer`: Groq draft with validator and template fallback (V5) |
| `app/groq_client.py` | Groq chat-completions client |
| `app/validator.py` | Rejects drafts that miss a chip or add a day, time, number or name |
| `app/templates.py` | Deterministic template sentence for any chip set |
| `app/bolna_agent.py` | Pure builder for the Path B graph agent (`bolna/agent.json`) |
| `app/bolna_client.py` | `HttpBolnaClient`: calls, events, agent and custom-model admin |
| `app/tts.py`, `app/sarvam.py` | Path A `POST /tts` via Sarvam Bulbul (A5) |
| `fakes/` | `FakeBolna` (plays Bolna's graph runtime over HTTP), `ScriptedBolna` (adds the §1 receptionist) and an SSE reader |
| `scripts/local_demo.py` | Free local backend for the whole §1 call; see [Local demo](#local-demo-no-bolna-no-cost) |
| `scripts/sign_lab.py`, `scripts/lab_composer.py`, `scripts/lab_voice.py` | The local demo with the real composer and voice for webcam tests; see [Sign Lab](#sign-lab-webcam-tests-with-the-real-composer-and-voice) |
| `scripts/compose_turns.py` | Evaluation turns from `spikes/recognition/video_eval.py`: recognised and ground-truth chips through the production composer, drafts to Sarvam WAVs, paid calls capped |
| `tools/`, `scripts/fake_app.py`, `scripts/voice_spike.py` | App-side client, PLAN §1 demo script, guided V4 checks (`uv run python -m scripts.fake_app …`) |
| `scripts/bolna_agent.py` | Render / register / create / update the Bolna agent (writes need `--yes`) |
| `scripts/heroku_*.sh` | Heroku deploy and config push; see [HEROKU.md](HEROKU.md) |
| `tests/e2e/` | PLAN §1 demo script and safety edge cases through the real app and `FakeBolna` |

## Running it locally

`uv run uvicorn app.main:app` builds the app from settings on first access:

- no `GROQ_API_KEY` → template drafts only;
- no `BOLNA_API_KEY` → `/calls` and the custom LLM answer 503;
- no `BOLNA_AGENT_ID` → the app boots (the custom LLM must be live before the agent is
  registered), `POST /calls` answers 502;
- empty `ALLOWED_RECIPIENTS` → every contact gets 403; a malformed entry stops the boot.

The full check, including the spikes and shell scripts, is `../scripts/verify.sh`.

## Local demo (no Bolna, no cost)

Runs the whole PLAN §1 clinic call on this Mac, for the iOS simulator
(`-IsharaDriver live`) or the Mac bridge. Nothing is dialled and no paid API is
reached:

```sh
cd backend
uv run python -m scripts.local_demo            # http://127.0.0.1:8000, token ishara-local-demo
uv run python -m scripts.local_demo --b24      # receptionist talks over the first SEND
```

```text
app / bridge ──POST /calls, WS──▶ real app (CallManager, template drafts)
                                   │  start_call, events     ▲ webhooks, custom-LLM POSTs
                                   ▼                         │
                                 ScriptedBolna: rings, answers, plays the receptionist
```

- `ScriptedBolna` answers after a ring, then says "We have 4 pm tomorrow. Does
  that work?" after the first spoken reply and "Yes, 10:30 tomorrow morning."
  after the second, as captions. Every approved reply is fetched from the
  server's own `/v1/chat/completions` over HTTP, so the backend path is the real
  one. What the agent "speaks" is printed as `agent says: …`.
- After 15 s with nobody talking (Bolna's silence repeat, scaled by `--delay`) it
  asks for the holding line. The app gets the disclosure, every holding line and
  the goodbye as `caption {speaker: "agent"}`.
- Settings are built in the script, not from `.env`: no Groq, Bolna or Sarvam key
  is set even if one is exported, so drafts come from the templates.
- It prints the base URL and app token. For the simulator put them in
  `ios/Ishara/Config/Secrets.xcconfig` (`ISHARA_BACKEND_URL = http:/$()/127.0.0.1:8000`,
  `ISHARA_APP_TOKEN = ishara-local-demo`); the simulator shares the Mac's network,
  so `127.0.0.1` works. A real iPhone can't reach it.
- Options: `--port`, `--app-token`, `--contact` (repeatable, default `clinic`;
  add `--contact clinic --contact mehta-office` to allow the app's second contact),
  `--b24` (first SEND of each call ends `not delivered` after 10 s, then SEND
  again), `--delay` (scales the pauses; `0.5` is twice as fast), `--receptionist`
  (`clinic`, the §1 lines above, by default; for Call for me, `offer`: "we have four
  pm tomorrow does that work", then "okay thank you bye"; `open-question`: "what time
  would you like to come in" first). She waits, saying nothing, while the agent asks
  her to hold on ("One moment, please.").
- One call at a time. Tests: `tests/test_local_demo.py`.

## Sign Lab (webcam tests with the real composer and voice)

The local demo, but drafting with the production Groq composer and speaking with
the real Sarvam voice on the Mac speakers, so signs from the Mac webcam can be
tested end to end without a phone call. From the repo root, one command:

```sh
scripts/sign_lab.sh            # Groq drafts + Sarvam voice (small cost, see below)
scripts/sign_lab.sh --free     # template drafts, no voice, no cost
```

```text
webcam ─▶ live_source.py ─▶ mac_bridge.py ──chips, SEND──▶ sign_lab backend (real app)
          (SignCLIP venv)        ▲                           │  composer: Groq → validator → template
                                 └──── drafts, captions ─────┤  LabBolna = ScriptedBolna:
                                                             │    receptionist lines → captions
                     Mac speakers ◀── afplay ◀── Sarvam ◀────┘    every line the agent speaks
```

- `sign_lab.sh` checks the bridge venv, the SignCLIP venv and the bundle
  (`spikes/recognition/artifacts/evidence/recognition-bundle-signclip.json`, or
  `--bundle PATH`) before starting anything, and prints the exact command to fix
  each. It starts the backend, waits for `/health`, then runs
  `mac_bridge.py --live --camera 0 --contact clinic --confirm-cost`. That flag only
  asks this local backend to start its scripted call: nothing is dialled. Ctrl-C
  stops both. Backend lines are prefixed `[lab]`.
- Other flags: `--camera N`, `--port N`, `--env-file PATH`, `--recognition-dir DIR`
  (a `spikes/recognition` with the venvs, e.g. the main checkout when running from
  a worktree), and `-- ARGS` for extra bridge args (`-- --replay-videos DIR`
  replaces the camera).
- Type the receptionist's lines yourself to check drafts against any reply. That
  needs two terminals, because the bridge reads SEND from its own:
  `scripts/sign_lab.sh --backend-only --receptionist manual` and
  `scripts/sign_lab.sh --bridge-only`. In the backend terminal, Enter sends a line
  as her words (a caption); `/silence` fires Bolna's silence repeat (holding line).
- The backend alone: `cd backend && uv run python -m scripts.sign_lab` with
  `--composer templates|groq`, `--voice none|sarvam`, `--receptionist script|manual`,
  `--env-file`, `--port`, `--delay`. Defaults are free (templates, silent, scripted).
- What it prints: `receptionist says`, `chips … (receptionist last said: …)`,
  `groq answered in X s: <raw>`, `draft (llm|template, X s)`, `  fallback: <why>`
  (the validator's reasons, a timeout or an error, exactly as production decides),
  `approved (SEND)`, `agent says`, `voice: playing (Sarvam TTS X s)` and
  `voice: done (afplay exit N)`.
- Keys: `GROQ_API_KEY` (and optional `GROQ_MODEL`) for `--composer groq`,
  `SARVAM_API_KEY` for `--voice sarvam`, read from the repo-root `.env` only (not
  exported variables), and only when those flags are given. No Bolna key is set.
- Costs: one Groq request per chip change (a fraction of a paisa each) and one
  Sarvam request per spoken line (about ₹0.1–0.5): the disclosure, each approved
  reply and the goodbye.
- Voice lines play one at a time and never block the server; a Sarvam failure skips
  that line and is printed. The receptionist herself is not voiced (read her
  captions, as the Deaf caller would).
- Tests: `tests/test_sign_lab.py`, `tests/test_lab_composer.py`,
  `tests/test_lab_voice.py`, `tests/test_sign_lab_script.py` (fake venvs, `--free`).
