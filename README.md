# Ishara

Ishara is a hackathon prototype for helping an ISL signer communicate with a
hearing person during an administrative appointment: recognize a bounded signed
concept, compose an explicitly intended sentence, let the user review it, then
produce speech.

**Start here: [teammate handoff](docs/HANDOFF.md).** It covers what works, the
measured results, research decisions, setup, repository layout and next tasks.
Updated 20 October 2026.

## Current capability

- A local browser diagnostic runs real SL-GCN recognition, fixed sentence
  templates, exact editing and single-use approval. It does not produce speech.
- SignCLIP reference matching ranked hello first for **7/7 saved intended-hello
  attempts**, compared with **0/7** for SL-GCN features using identical references.
  This is a five-concept development comparison. Rejection and fresh-session
  recognition remain unvalidated; every retrieval replay abstains.
- Capture, landmark review and session-separated calibration/evaluation tools
  are ready for fresh recordings.
- **34 recognition/backend tests and 13 offline call-flow tests pass locally.**
  The browser flow passed 20 checks in Helium.
- Bolna speech, call-audio delivery, camera/caption coexistence and Deaf participant
  usability remain unresolved. There is no end-to-end validated product yet.

Meaningful Bolna integration is mandatory. The preferred target is an existing
user-started, own-number Phone call; Bolna must not originate a duplicate call.
Any app-owned or service-originated call would be an explicit product pivot.

## Read and run

- [Handoff and fresh-checkout setup](docs/HANDOFF.md)
- [Current plan and acceptance gates](PLAN.md)
- [Recognition tooling and detailed measurements](spikes/recognition/README.md)
- [Bolna and iPhone diagnostic harness](spikes/call_flow/README.md)
- [Research index](docs/RESEARCH.md) and [claim ledger](docs/CLAIM-LEDGER.md)
- [Original research links](research-links.md)

The current implementation is on `spike/slgcn-miniature`. Experiments run locally
on the Mac; a production mobile app and final architecture have not been approved.
Model weights, recordings, credentials and generated artifacts are excluded from
Git. Setup scripts fetch public assets; the handoff distinguishes those from
private development footage that a fresh checkout will not contain.
