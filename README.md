# Ishara

Ishara is a hackathon prototype for helping an ISL signer communicate during a
seated administrative appointment: recognize a supported signed concept, compose
an explicitly intended sentence, let the user review it, then produce speech.

**Current phase:** backend ML feasibility and separate speech/device diagnostics.
The local diagnostic pipeline runs; recognition and end-to-end calling have not
passed their validation gates.

## Start here

1. [Handoff](docs/HANDOFF.md) — current capability, chosen direction and open questions.
2. [Plan](PLAN.md) — active tasks and acceptance criteria.
3. [Recognition runbook](spikes/recognition/README.md) or
   [call-flow runbook](spikes/call_flow/README.md) — install and run the tools.

The implementation is on `spike/slgcn-miniature`. Model assets, private recordings
and credentials are excluded from Git; the runbooks explain what setup fetches.

## Reference

- [Workflow and diagrams](docs/WORKFLOW.md): proposed product flow and boundaries.
- [Experiment record](docs/experiments/recognition.md): measured ML results and their limits.
- [Research index](docs/research/README.md): methods, datasets, source audits and product research.
- [Source claim ledger](docs/CLAIM-LEDGER.md): dated source claims and qualifications.
- [Archive](docs/archive/README.md): superseded plans and historical notebooks.

Meaningful Bolna integration is mandatory. The preferred target is an existing,
user-started own-number Phone call. Bolna must not originate a duplicate call;
any app-owned or service-originated route is an explicit product pivot.
