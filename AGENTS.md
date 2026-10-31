# Ishara project navigation

## Current phase and controlling constraints

- **Phase: launch** (from 31 October 2026; the 23–31 October demo build is done). The product is the steer call (D10). [README.md](README.md) is the source for the product, architecture, setup and deployment; [PLAN.md](PLAN.md) owns the decisions. Public positioning lives in README, [PITCH.md](PITCH.md), [MARKET.md](MARKET.md) and [docs/demo/](docs/demo/SUBMISSION.md); keep them consistent.
- **Recognition (decision D8, 25 Oct):** pure ASL, using the public Kaggle ASL Signs 1st-place model as is (no own recordings, no training, no fine-tuning, no reference clips). Open-set rule: full 250-way softmax, never restricted to the vocabulary first; chip only for a bundle-vocabulary gloss at margin ≥ 0.3 and p ≥ its cut-off. Since 28 Oct the vocabulary is the rehearsed words minus morning (hello, thankyou, yes, no, now, please, tomorrow, wait) with the provisional public-clip cut-offs (global 0.65, per-word 0.45–0.6); they were set on public clips. Morning is out because the model learned the one-handed MORNING, not the two-handed dictionary form; it comes back only if it chips on the iPhone with no wrong words. The bundle lives in `spikes/recognition/fixtures/asl/` and `ios/Ishara/Resources/asl-bundle.json` (identical, tested). Measurements: [docs/experiments/asl-model-probe.md](docs/experiments/asl-model-probe.md); how it was built: [the archived handoff](docs/archive/handoffs/2026-10-26-ready-made-asl-recognizer.md).
- **Call path (decision D1, Option C):** build Path B first. Bolna places the call from its default number, the backend acts as Bolna's custom LLM, and the app sends approved text via graph events. Path A (the user's own-number Phone call plus Apple Add Audio in Calls) is a bonus only if everything else lands by Wednesday 28 Oct. Always disclose that Path B calls come from Ishara's calling number, which Bolna provides, not the user's own number. The app says "Ishara's calling number" (founder's decision on issue #51, 28 Oct); docs, the pitch and the submission say plainly that it is a Bolna number. The Bolna account is on trial, so it only dials numbers verified in the Bolna dashboard.
- **Relay calls (the classic flow, `-IsharaFlow classic`): nothing is spoken unless the user taps SEND.** Approvals are single use and tied to a `turn_id`. Unsure recognition, stale drafts, network failure and ended calls stay silent; never guess.
- **Steer calls (decision D10, 30 Oct): the typed request is the approval.** Ishara may accept only offers that fit it, share only what the user gave (an attached document is quoted word for word, only when asked), and must defer anything else. Ishara's proposed line waits a fixed 2 s (`STEER_WINDOW_S`, founder, 31 Oct) for the user to tap and edit it, then is spoken. A user's typed or signed line is polished without new facts, previewed for 1.5 s, then spoken. Filler lines carry no facts.
- **The LLM composer (Groq, `openai/gpt-oss-120b`) may reword but not add facts.** A validator rejects missing chip meanings and any invented day, time, number or name; templates are the fallback (also when Groq is slower than 1.5 s or has no key).
- **Calls:** only to numbers in `ALLOWED_RECIPIENTS` (consenting teammates; comma-separated `contact_id=+E164` entries, e.g. contact id `clinic`; the app sends a contact id or a typed number, and a typed number is dialled only if it is on the list), with synthetic appointment details. Never place an unexpected or third-party call. Give a cost heads-up before paid runs. Placing calls, paid inference, device installations and deployments need explicit task authorization; a task in `PLAN.md` is not authorization by itself.
- **Buildathon rule:** any project with a voice component qualifies; Bolna is not mandatory by the rules. The team chose Bolna (Sarvam voice, Deepgram ASR, Plivo line) anyway.
- **Hosting:** the backend runs on Heroku (EU region) with a Basic dyno or higher, deployed by pushing `backend/` as a `git subtree`. Eco dynos sleep, and a sleeping custom-LLM endpoint means silence on the call. Run exactly one dyno and one uvicorn worker (`--workers 1` in the Procfile, `WEB_CONCURRENCY=1` as a backup): call state is in memory, and two workers split a call (seen live 28 Oct). API keys stay on the backend, never in the iOS app.
- **Device:** the founder's iPhone 17; calls from the iPhone and recognition on the iPhone are done ([issue #72](https://github.com/BishalJena/ishara/issues/72), 31 Oct). Other work runs in the iOS simulator with saved videos (no camera, no Phone-app calls; it can start Path B calls through the backend, as on 28 Oct). The app needs `ios/Packages/SignPipelineLiteRT/Scripts/download_tflite_c.sh` run once (verify.sh does it) and the models in `ios/Ishara/LocalAssets/` (see its README).
- No Deaf participant validation. Don't present the personalised 12-sign pilot, hearing reenactment or isolated-sign benchmarks as validated natural conversation or usability.
- No secret keys, account identifiers, telephone values, raw account responses or private credential paths in repository artifacts.

## Verify before committing

- Everything: `scripts/verify.sh` (add `--keep-going` to see every failure). Missing tools or parts show as `SKIPPED`. Light recognition tests need `spikes/recognition/.venv-light` or the full `.venv`.
- Backend: `cd backend && uv run ruff format --check . && uv run ruff check . && uv run pytest -q`
- Env names are listed in `.env.example`; `cd backend && uv run python -m app.config` shows which are set.
- Heroku deploys follow `backend/HEROKU.md` and still need explicit deploy authorization.

## Where to look

- [Active plan: decisions, tasks, gates, tests](PLAN.md)
- [README: the call flow, architecture, setup and deployment](README.md) (it is also the teammate handoff)
- [Deploying the backend to Heroku](backend/HEROKU.md) and [the Bolna agent](backend/bolna/README.md)
- [How to test Ishara](docs/TESTING.md)
- [Measured ML results and limits](docs/experiments/recognition.md)
- [Recognition commands](spikes/recognition/README.md)
- [Research reading guide](docs/research/README.md)
- [Claim ledger and external source inventory](docs/CLAIM-LEDGER.md)
- [Archive: snapshots, the 28 Oct handoff and workflow, the old architecture board, earlier plans and experiments](docs/archive/README.md): earlier constraints (own-number only, mandatory Bolna, no Bolna-originated calls) are superseded by the 23 October decisions.

Use Exa for web source discovery and Context7 first for library/framework/SDK/API/CLI/cloud documentation. Start with resolve-library-id unless an exact library ID is supplied, then query a scoped concept. Verify current primary pages when indexed documentation is stale or contradictory. Bolna's docs index is `https://www.bolna.ai/docs/llms.txt`; every page is available as `.md`. Distinguish documented capability, author-reported benchmarks, executed observations and hypotheses.

## graphify

When the user types `/graphify`, invoke the graphify skill before other work. The user's supplied skill location is `~/.Codex/skills/graphify/SKILL.md`; if that path is stale, use the available skill catalog to locate it. Use a Skill tool when available; do not invent a tool that is absent.
