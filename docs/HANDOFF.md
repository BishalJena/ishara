# Teammate handoff

Current state: **20 October 2026**, branch `spike/slgcn-miniature`.
This file owns the current capability and direction. Detailed measurements belong
in the [experiment record](experiments/recognition.md), active tasks in
[PLAN.md](../PLAN.md), and commands in the spike runbooks.

## What works

- The Mac browser diagnostic runs real OpenHands SL-GCN predictions on saved clips,
  fixed sentence templates, exact editing and single-use approval.
- The separate SignCLIP experiment produces real local embeddings and compares
  clips with labeled ISL references. Its replay outputs deliberately abstain.
- Capture, landmark-overlay review, explicit label verification and
  session-separated calibration/evaluation tools are implemented.
- The speech track has an offline lifecycle mock, a non-telephony Bolna probe and
  an Apple audio/camera diagnostic harness. These are separate tools.

## Current direction and blockers

**SignCLIP is the leading representation for fresh-data evaluation.** Reference
matching improved the ranking of the saved intended-hello attempts, but those
recordings cover one intended meaning. Unknown-sign rejection remains unresolved,
and whole-clip extraction has not met the live response target.

The next vocabulary is hello, thankyou, doctor, hospital and tomorrow, for one
seated signer and one complete sign at a time. The older browser diagnostic also
supports today and location. Its recognizer is still SL-GCN; uncalibrated
SignCLIP ranks are not connected to composition or speech.

**Fixed intent templates are the default composer.** The earlier Qwen experiment
changed the meaning of a requested-day example. Templates require explicit purpose,
block conflicts and retain user editing and approval. Neither composer can repair
an incorrectly recognized concept. The LLM remains an optional experiment.

**Bolna speech and existing-call delivery are unproven.** The provider probe has
not produced usable speech. The iPhone harness has been built, but physical
call/camera/caption coexistence has not been demonstrated. An offline mock or
Apple local voice does not establish Bolna integration.

There is no end-to-end validated product, trained personalized model or Deaf
participant validation. See the [workflow](WORKFLOW.md) for the proposed composition.

## Start working

Clone this branch, or fetch and switch to it after preserving local work:

```sh
git clone --branch spike/slgcn-miniature git@github.com:BishalJena/ishara.git
cd ishara
```

Then follow the runbook for the relevant track:

- [Recognition](../spikes/recognition/README.md): environment setup, public clips,
  browser miniature, SignCLIP comparison, capture and evaluation.
- [Speech/device](../spikes/call_flow/README.md): offline tests, provider probe
  boundaries and the iPhone diagnostic.

The repository is private. Weights, recordings, credentials, generated evidence
and signing identities are excluded. Setup fetches public assets; a fresh clone
does not contain the private footage behind the recorded webcam results.
Mac/Python 3.11 is the tested ML setup; other platforms are unverified.

The immediate human input is fresh, correctly labeled signing. Begin with three
takes per concept, review tracking and sign forms, then follow the separate-session
calibration and final-test gates in the plan. The speech track can independently
work with fixed, approved synthetic text.

## Reading map

- [Research index](research/README.md): why these methods were selected and where
  the primary evidence lives.
- [Experiment record](experiments/recognition.md): actual results, regressions,
  timing, validation counts and reproducibility limits.
- [Source claim ledger](CLAIM-LEDGER.md): dated platform/provider claims.
- [Archive](archive/README.md): earlier proposals and completed task notebooks.

The preferred product remains one seated administrative appointment conversation.
Meaningful Bolna integration is mandatory. The user starts their ordinary
own-number Phone call; Bolna must not create a duplicate call. Any service-owned
call is a disclosed pivot. System captions are visible to the user, not a proven
source of transcript text for Ishara.
