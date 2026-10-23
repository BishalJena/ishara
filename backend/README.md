# Ishara backend

FastAPI service for Path B ([PLAN.md §3](../PLAN.md#3-architecture)): app sessions,
the Cerebras composer and Bolna's custom-LLM endpoint. Python 3.11, managed with `uv`.

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
| `app/protocol.py` | App ↔ backend messages, the 12-sign vocabulary, composer request/draft |
| `app/markers.py` | Marker block in Bolna node prompts that ties custom-LLM requests to a call and turn |
| `app/ports.py` | `Composer`, `BolnaClient`, `CallLedger` interfaces between modules |
| `app/auth.py` | `APP_TOKEN` and `CUSTOM_LLM_TOKEN` bearer checks |
| `app/main.py` | `create_app(...)`, `/health`, router wiring |
| `app/calls.py` | Session layer: `POST /calls`, app WebSocket, `CallLedger` (V6) |
| `app/custom_llm.py` | `POST /v1/chat/completions` for Bolna (V2) |
| `app/tts.py` | Path A `POST /tts` via Sarvam (A5) |
