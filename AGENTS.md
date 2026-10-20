# Ishara project navigation

## Current phase and controlling constraints

- The user has authorized and begun the backend ML feasibility prototype: local recognition comparisons, capture/review, sentence composition and approval, alongside the separate Bolna/device diagnostics. Follow the active section in `PLAN.md`; defer polished app UX and do not imply that recognition or the call flow has passed its validation gates.
- Do not route the user's target call through Bolna or have Bolna place a second call. The preferred target remains an ordinary own-number Phone call with speech injected into that existing call. Clearly label any app-owned-call pivot.
- An actual cellular test must use the user's normal line, synthetic content and a consenting recipient; never initiate an unexpected Bolna-originated call.
- Meaningful Bolna integration is **mandatory**, confirmed by the user. Ordinary own-number Phone calls remain preferred; the user now permits research into explicit product/workflow pivots when needed. Label app-owned/service-originated calling or delegation as deviations rather than claiming they preserve native calling.
- iPhone 17 is confirmed; installed iOS is unknown. Camera + AAC speech injection + system captions are untested together. User-visible system captions are not an app-readable transcript.
- No Deaf participant validation. Do not present source research, hearing reenactment or isolated-sign benchmarks as validated natural conversation or usability.
- No secret keys, account identifiers, telephone values, raw account responses or private credential paths in repository artifacts. Calls, paid inference, installations and deployments need task authorization.

## Where to look

- [Teammate handoff: capability, setup, research and next steps](docs/HANDOFF.md)
- [Research reading guide](docs/research/README.md)
- [Product recommendation and alternatives](docs/research/product-directions.md)
- [Measured ML results and limits](docs/experiments/recognition.md)
- [Recognition commands](spikes/recognition/README.md)
- [Bolna/device commands](spikes/call_flow/README.md)
- [Earlier feasibility synthesis](docs/archive/2026-10-18-feasibility.md) — historical hard no-pivot constraint and unknown mandatory-Bolna status are superseded by the latest user instruction above.
- [Claim ledger and external source inventory](docs/CLAIM-LEDGER.md)
- [Provisional user workflow](docs/WORKFLOW.md)
- [Active tasks and validation gates](PLAN.md)
- [Historical plans and experiment notebooks](docs/archive/README.md)

Current recommendation is one user-controlled administrative appointment conversation, demonstrated seated with a propped phone. Preserve native calling if meaningful Bolna OSS speech orchestration and device composition prove out; an app-owned Bolna call is an explicit conditional pivot. No architecture has been approved. Bolna OSS text/audio/marks/clear primitives exist but routing/lifecycle defects require engineering; absence of a hosted standalone TTS endpoint does not mean there is no source-integration path.

Use Exa for web source discovery and Context7 first for library/framework/SDK/API/CLI/cloud documentation. Start with resolve-library-id unless an exact library ID is supplied, then query a scoped concept. Verify current primary pages when indexed documentation is stale or contradictory. Distinguish documented capability, author-reported benchmarks, executed observations and hypotheses.

## graphify

When the user types `/graphify`, invoke the graphify skill before other work. The user's supplied skill location is `~/.Codex/skills/graphify/SKILL.md`; if that path is stale, use the available skill catalog to locate it. Use a Skill tool when available; do not invent a tool that is absent.
