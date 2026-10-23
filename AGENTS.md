# Ishara project navigation

## Current phase and controlling constraints

- **Phase: demo build** (23–31 October 2026). Follow [PLAN.md](PLAN.md): its decisions, day-by-day tasks and gates are the source of truth. The goal is a demo-ready app with about 12 signs and one rehearsed clinic call, not a complete product.
- **Call path (decision D1, Option C):** build Path B first. Bolna places the call from its default number, the backend acts as Bolna's custom LLM, and the app sends approved text via graph events. Path A (the user's own-number Phone call plus Apple Add Audio in Calls) is a Thursday bonus. Always disclose that Path B calls come from a Bolna number, not the user's own number.
- **Nothing is spoken unless the user taps SEND.** Approvals are single use and tied to a `turn_id`. Unsure recognition, stale drafts, network failure and ended calls stay silent; never guess.
- **The LLM composer (Cerebras) may reword but not add facts.** A validator rejects missing chip meanings and any invented day, time, number or name; templates are the fallback.
- **Calls:** only to numbers in `ALLOWED_RECIPIENTS` (consenting teammates), with synthetic appointment details. Never place an unexpected or third-party call. Give a cost heads-up before paid runs.
- **Buildathon rule:** any project with a voice component qualifies; Bolna is not mandatory by the rules. The team chose Bolna (Sarvam voice, Deepgram ASR, Plivo line) anyway.
- **Hosting:** the backend runs on Heroku with a Basic dyno or higher. Eco dynos sleep, and a sleeping custom-LLM endpoint means silence on the call. API keys stay on the backend, never in the iOS app.
- **Device:** iPhone 17 (teammate's, from Thursday); installed iOS unknown. Until then use the iOS simulator with saved videos; it has no camera and cannot place calls.
- No Deaf participant validation. Don't present the personalised 12-sign pilot, hearing reenactment or isolated-sign benchmarks as validated natural conversation or usability.
- No secret keys, account identifiers, telephone values, raw account responses or private credential paths in repository artifacts.

## Where to look

- [Active plan: decisions, tasks, gates, tests](PLAN.md)
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
