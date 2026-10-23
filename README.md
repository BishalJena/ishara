# Ishara

Ishara is a hackathon prototype that lets an Indian Sign Language (ISL) signer
handle a short phone call: the iPhone recognises a small set of signs, drafts a
sentence, the user approves it, and a voice speaks it into the call. The
receptionist's reply comes back as captions.

**Current phase: demo build** for the Bolna Symphony buildathon (submission
31 October 2026). Target: about 12 signs and one rehearsed clinic-appointment call.

## Start here

1. [Plan](PLAN.md): decisions, architecture, day-by-day tasks and gates.
2. [Architecture board](docs/architecture/README.md): the same plan as an Excalidraw diagram.
3. [Handoff](docs/HANDOFF.md): what already works and how to set it up.
4. Runbooks: [recognition](spikes/recognition/README.md) and
   [call-flow / device harness](spikes/call_flow/README.md).

Model assets, private recordings and credentials are excluded from Git; the
runbooks explain what setup fetches.

## How it works (short version)

- **On the iPhone:** MediaPipe Holistic → start/stop detector → SignCLIP (Core ML)
  → word chips → draft → **SEND**.
- **Backend (Heroku):** a Cerebras-drafted sentence with a validator and template
  fallback; Bolna's custom-LLM endpoint; call and turn state.
- **Bolna:** places the call (Path B), speaks with a Sarvam voice and transcribes the
  receptionist with Deepgram. Path A, the user's own-number call with Apple's
  call-audio injection, is a bonus mode.

## Reference

- [Workflow and edge cases](docs/WORKFLOW.md)
- [Experiment record](docs/experiments/recognition.md): measured ML results and their limits.
- [Research index](docs/research/README.md): methods, datasets, source audits and product research.
- [Source claim ledger](docs/CLAIM-LEDGER.md): dated source claims and qualifications.
- [Archive](docs/archive/README.md): superseded plans and historical notebooks.
