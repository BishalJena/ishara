# Ishara project navigation

## Current phase and controlling constraints

- **Phase: demo build** (23–31 October 2026). Follow [PLAN.md](PLAN.md): its decisions, day-by-day tasks and gates are the source of truth. The goal is a demo-ready app with a small rehearsed sign vocabulary and one rehearsed clinic call, not a complete product.
- **Recognition (decision D8, 25 Oct):** pure ASL, using the public Kaggle ASL Signs 1st-place model as is (no own recordings, no training, no fine-tuning, no reference clips). Open-set rule: full 250-way softmax, never restricted to the vocabulary first; chip only for a bundle-vocabulary gloss at margin ≥ 0.3 and p ≥ its cut-off. Since 28 Oct the vocabulary is the rehearsed words minus morning (hello, thankyou, yes, no, now, please, tomorrow, wait) with the provisional public-clip cut-offs (global 0.65, per-word 0.45–0.6); the iPhone clips decide the final values. Morning is out because the model learned the one-handed MORNING, not the two-handed dictionary form; it comes back only if the iPhone test ([issue #72](https://github.com/BishalJena/ishara/issues/72)) shows it chips with no wrong words. The bundle lives in `spikes/recognition/fixtures/asl/` and `ios/Ishara/Resources/asl-bundle.json` (identical, tested). Measurements: [docs/experiments/asl-model-probe.md](docs/experiments/asl-model-probe.md); plan: [docs/handoffs/2026-10-26-ready-made-asl-recognizer.md](docs/handoffs/2026-10-26-ready-made-asl-recognizer.md).
- **Call path (decision D1, Option C):** build Path B first. Bolna places the call from its default number, the backend acts as Bolna's custom LLM, and the app sends approved text via graph events. Path A (the user's own-number Phone call plus Apple Add Audio in Calls) is a bonus only if everything else lands by Wednesday 28 Oct. Always disclose that Path B calls come from Ishara's calling number, which Bolna provides, not the user's own number. The app says "Ishara's calling number" (founder's decision on issue #51, 28 Oct); docs, the pitch and the submission say plainly that it is a Bolna number. The Bolna account is on trial, so it only dials numbers verified in the Bolna dashboard.
- **Nothing is spoken unless the user taps SEND.** Approvals are single use and tied to a `turn_id`. Unsure recognition, stale drafts, network failure and ended calls stay silent; never guess.
- **The LLM composer (Groq, `openai/gpt-oss-120b`) may reword but not add facts.** A validator rejects missing chip meanings and any invented day, time, number or name; templates are the fallback (also when Groq is slower than 1.5 s or has no key).
- **Calls:** only to numbers in `ALLOWED_RECIPIENTS` (consenting teammates; comma-separated `contact_id=+E164` entries, e.g. contact id `clinic`, so the app sends only the contact id), with synthetic appointment details. Never place an unexpected or third-party call. Give a cost heads-up before paid runs. Placing calls, paid inference, device installations and deployments need explicit task authorization; a task in `PLAN.md` is not authorization by itself.
- **Buildathon rule:** any project with a voice component qualifies; Bolna is not mandatory by the rules. The team chose Bolna (Sarvam voice, Deepgram ASR, Plivo line) anyway.
- **Hosting:** the backend runs on Heroku (EU region) with a Basic dyno or higher, deployed by pushing `backend/` as a `git subtree`. Eco dynos sleep, and a sleeping custom-LLM endpoint means silence on the call. Run exactly one dyno and one uvicorn worker (`--workers 1` in the Procfile, `WEB_CONCURRENCY=1` as a backup): call state is in memory, and two workers split a call (seen live 28 Oct). API keys stay on the backend, never in the iOS app.
- **Device:** the founder's iPhone 17; device work (phone clips, install, speed) happens when it is available, following [issue #72](https://github.com/BishalJena/ishara/issues/72). Everything else runs in the iOS simulator with saved videos (no camera, no Phone-app calls; it can start Path B calls through the backend, as on 28 Oct). The app needs `ios/Packages/SignPipelineLiteRT/Scripts/download_tflite_c.sh` run once (verify.sh does it) and the models in `ios/Ishara/LocalAssets/` (see its README).
- No Deaf participant validation. Don't present the personalised 12-sign pilot, hearing reenactment or isolated-sign benchmarks as validated natural conversation or usability.
- No secret keys, account identifiers, telephone values, raw account responses or private credential paths in repository artifacts.

## Verify before committing

- Everything: `scripts/verify.sh` (add `--keep-going` to see every failure). Missing tools or parts show as `SKIPPED`. Light recognition tests need `spikes/recognition/.venv-light` or the full `.venv`.
- Backend: `cd backend && uv run ruff format --check . && uv run ruff check . && uv run pytest -q`
- Env names are listed in `.env.example`; `cd backend && uv run python -m app.config` shows which are set.
- Heroku deploys follow `backend/HEROKU.md` and still need explicit deploy authorization.

## Where to look

- [Active plan: decisions, tasks, gates, tests](PLAN.md)
- [Latest system state snapshot (28 Oct)](docs/status/2026-10-28.md); earlier: [25 Oct](docs/status/2026-10-25.md)
- [Architecture board (Excalidraw)](docs/architecture/README.md)
- [Current workflow and edge cases](docs/WORKFLOW.md)
- [Teammate handoff: capability and setup](docs/HANDOFF.md)
- [Measured ML results and limits](docs/experiments/recognition.md)
- [Recognition commands](spikes/recognition/README.md)
- [Bolna/device spike commands](spikes/call_flow/README.md)
- [Research reading guide](docs/research/README.md)
- [Claim ledger and external source inventory](docs/CLAIM-LEDGER.md)
- [Historical plans and experiment notebooks](docs/archive/README.md): earlier constraints (own-number only, mandatory Bolna, no Bolna-originated calls) are superseded by the 23 October decisions.

Use Exa for web source discovery and Context7 first for library/framework/SDK/API/CLI/cloud documentation. Start with resolve-library-id unless an exact library ID is supplied, then query a scoped concept. Verify current primary pages when indexed documentation is stale or contradictory. Bolna's docs index is `https://www.bolna.ai/docs/llms.txt`; every page is available as `.md`. Distinguish documented capability, author-reported benchmarks, executed observations and hypotheses.

## graphify

When the user types `/graphify`, invoke the graphify skill before other work. The user's supplied skill location is `~/.Codex/skills/graphify/SKILL.md`; if that path is stale, use the available skill catalog to locate it. Use a Skill tool when available; do not invent a tool that is absent.
