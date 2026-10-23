# Deploying the backend to Heroku

Runbook for V1 in [PLAN.md](../PLAN.md). Deploying needs explicit authorization (PLAN §10);
this file and the scripts don't do anything on their own. Never commit the app name, keys
or phone numbers; they live in your shell, the repo-root `.env` and Heroku config only.

```text
repo (monorepo)                         Heroku app
├── backend/   ── git subtree split ──▶  /  (pyproject.toml, uv.lock, .python-version, Procfile)
├── ios/                                 └─ Python buildpack: uv sync --locked --no-default-groups
└── spikes/                                  web: uvicorn app.main:app ... (Basic dyno, never Eco)
```

## How it builds

- The stock `heroku/python` buildpack supports uv (since May 2025). It needs `pyproject.toml`,
  `uv.lock` and `.python-version` at the app root; `backend/` already has all three, so no
  extra files are needed. Python comes from `.python-version` (3.11).
- Heroku runs `uv sync --locked --no-default-groups`, so the `dev` group (pytest, ruff) is not
  installed, and the build fails if `uv.lock` is out of date. Don't add a `requirements.txt`
  to `backend/`: the buildpack refuses more than one package manager file.
- Heroku builds from the root of what is pushed, so `heroku_deploy.sh` pushes only `backend/`
  using `git subtree split --prefix backend HEAD` (no monorepo buildpack needed). Only
  **committed** code is deployed; the script refuses uncommitted changes in `backend/`.

## One-time setup

1. Install the [Heroku CLI](https://devcenter.heroku.com/articles/heroku-cli) and run
   `heroku login`. Pick an app name and keep it out of the repo:

   ```sh
   export APP=your-app-name
   heroku create "$APP" --no-remote --buildpack heroku/python
   ```

   The common runtime offers `us` (default) and `eu` regions (`--region eu`). EU is closer to
   India; the latency difference for Bolna has not been measured.

2. Set config vars from the repo-root `.env`. The script sends exactly the names in
   `.env.example` (today: `APP_TOKEN`, `BOLNA_API_KEY`, `BOLNA_AGENT_ID`, `CUSTOM_LLM_TOKEN`,
   `GROQ_API_KEY`, `GROQ_MODEL`, `SARVAM_API_KEY`, `ALLOWED_RECIPIENTS`, `PUBLIC_BASE_URL`),
   skips empty ones, never sends `HEROKU_*` names, and never prints values:

   ```sh
   backend/scripts/heroku_config_push.sh --app "$APP"        # dry run: names only
   backend/scripts/heroku_config_push.sh --app "$APP" --yes  # sets them (restarts dynos)
   heroku config --app "$APP" --shell | cut -d= -f1          # check names, not values
   ```

   `PUBLIC_BASE_URL` is the app's `web_url` (`heroku info -s --app "$APP" | grep web_url`).
   Put it in `.env` and push again once the app exists.

3. First deploy, then make sure the web dyno is **Basic**, not Eco:

   ```sh
   backend/scripts/heroku_deploy.sh --app "$APP" --yes
   heroku ps:type web=basic --app "$APP"   # only if the script says the app is on Eco
   heroku ps:type --app "$APP"             # size column must say Basic (or larger)
   ```

   A new app has no dynos until its first build, so the script checks the dyno type before
   and after pushing. If the account defaults to Eco, the first run pushes, then stops with
   the `ps:type` command to run. Eco dynos sleep after 30 idle minutes, and a sleeping
   custom-LLM endpoint means silence on the call. Basic is listed at about $7/month by the CLI
   (check current pricing before switching).

## Every deploy

```sh
git switch <branch-to-deploy> && git status       # backend/ must be committed
backend/scripts/heroku_deploy.sh --app "$APP" --yes
```

It force-pushes the split `backend/` tree to the app's `main` branch (each split has fresh
history), waits for `/health` and prints only:

```text
status: ok
missing_config: GROQ_API_KEY      # names only; "none" when every required key is set
```

Useful checks:

```sh
curl -s "https://<web_url host>/health"
heroku logs --tail --app "$APP"
heroku releases --app "$APP"      # roll back with: heroku rollback vNN --app "$APP"
heroku ps --app "$APP"
```

## Router limits that matter for calls and the app WebSocket

- **30 s to first byte**: an HTTP request (for example Bolna's `/v1/chat/completions`) must
  start sending data within 30 s, else the router returns H12. Streamed replies are fine.
- **55 s rolling idle window**: after the first byte, the connection is dropped if neither
  side sends anything for 55 s (H15/H28). This applies to WebSockets too. The `Procfile`
  already runs uvicorn with `--ws-ping-interval 20 --ws-ping-timeout 20`, so idle app
  sockets stay open; clients should still reconnect on close.
- **90 s pooled-connection idle timeout**: uvicorn's default keep-alive (5 s) is shorter, which
  Heroku warns can cause occasional H13/H18 errors, so the `Procfile` sets
  `--timeout-keep-alive 95` (longer than the router's 90 s).
- Dynos restart at least once a day and on every config change or deploy. Anything held only
  in memory (open sockets, in-flight calls) is lost then, so avoid deploying or changing
  config during a rehearsal or call, and keep a single web dyno if call state is in memory.

Sources: [uv support](https://devcenter.heroku.com/changelog-items/3238),
[Python behavior](https://devcenter.heroku.com/articles/python-behavior-in-heroku),
[buildpack README](https://github.com/heroku/heroku-buildpack-python),
[HTTP routing timeouts](https://devcenter.heroku.com/articles/http-routing),
[WebSockets](https://devcenter.heroku.com/articles/websockets),
[deploying with Git](https://devcenter.heroku.com/articles/git).
