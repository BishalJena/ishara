# Ishara backend

FastAPI service for Path B ([PLAN.md §3](../PLAN.md#3-architecture)): app sessions,
the Groq composer and Bolna's custom-LLM endpoint. Python 3.11, managed with `uv`.

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
| `app/protocol.py` | App ↔ backend messages, the 12-sign vocabulary, composer request/draft |
| `app/markers.py` | Marker block in Bolna node prompts that ties custom-LLM requests to a call and turn; event, property and webhook path names |
| `app/ports.py` | `Composer`, `BolnaClient` (+ its `BolnaError`), `CallLedger` interfaces between modules |
| `app/auth.py` | `APP_TOKEN` and `CUSTOM_LLM_TOKEN` bearer checks |
| `app/calls.py` | Session layer I/O: `POST /calls`, app WebSocket, Bolna status webhook, `CallLedger` (V6) |
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
- Settings are built in the script, not from `.env`: no Groq, Bolna or Sarvam key
  is set even if one is exported, so drafts come from the templates.
- It prints the base URL and app token. For the simulator put them in
  `ios/Ishara/Config/Secrets.xcconfig` (`ISHARA_BACKEND_URL = http:/$()/127.0.0.1:8000`,
  `ISHARA_APP_TOKEN = ishara-local-demo`); the simulator shares the Mac's network,
  so `127.0.0.1` works. A real iPhone can't reach it.
- Options: `--port`, `--app-token`, `--contact` (repeatable, default `clinic`;
  add `--contact clinic --contact mehta-office` to allow the app's second contact),
  `--b24` (first SEND of each call ends `not delivered` after 10 s, then SEND
  again), `--delay` (scales the pauses; `0.5` is twice as fast).
- One call at a time. Tests: `tests/test_local_demo.py`.
