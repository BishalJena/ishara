# Ishara research entrypoint

> Historical sequence of research updates. Use the [research index](../research/README.md)
> for navigation and the [handoff](2026-10-28-handoff.md) for the current state.

New to the project? Start with the [teammate handoff](2026-10-28-handoff.md) for current
capability, execution results, setup and next tasks. This index preserves the
dated research and corrections that led to those decisions.

## Executed reference-matching follow-up — 20 October 2026

SignCLIP multilingual now runs locally with pinned source and checkpoint.
Against the same five-concept public reference bank, its top match was hello for
7/7 saved intended-hello attempts; SL-GCN features achieved 0/7. Public queries
with another same-label reference scored 5/6 and 6/6 respectively, excluding the
query itself. This is a development comparison, not an acceptance test.

Unknown-sign rejection remains unresolved: an out-of-scope today clip matched
hello at 0.931 similarity, above the 0.532–0.590 for the intended hello attempts.
All retrieval replay outputs abstain. SignCLIP's original landmark extraction
took a median 2.93 s on the webcam clips, so live latency is also unproven.

The fresh capture/review and session-separated calibration/evaluation tools are
implemented. The prototype now defaults to deterministic intent templates, fixing
the observed today-to-question behavior for the supported sentence fixtures.
The LLM remains optional; no fresh user recordings, training, Bolna speech or
call integration ran in this follow-up. See [PLAN.md](../../PLAN.md) and the
[recognition spike README](../../spikes/recognition/README.md) for current commands.
The earlier paused/LLM-default statements below describe their dated checkpoints.

## Independent Ishaara AI audit — 20 October 2026

[Website, paper and repository audit](../research/recognition/ishaara-ai-audit.md)
distinguishes the released six-class GRU from the current eighteen-label YOLO
browser pipeline. Real trained artifacts exist; the public evidence does not
establish general ISL translation, independent-signer reliability or our
appointment vocabulary. The report checks exact input/output contracts, metric
provenance, evaluation defects, sentence safeguards and practical reuse limits.
This was source/artifact inspection, not a new recognition benchmark.

## ASL transfer follow-up — 20 October 2026

[ASL transfer for Ishara](../research/recognition/asl-transfer.md) checks whether
sign-specific pretraining and a few ISL references can reduce our target-data
needs. CISLR provides direct ASL-to-ISL prototype evidence; SignCLIP provides a
released multilingual candidate with ISL in its inventory. The proposed next
experiment is reference matching against the existing SL-GCN baseline, before
committing to classifier training. The local recognition failures, semantic
limitations and call-path gates below remain unresolved.

## Executed miniature — 20 October 2026

The user authorized a local prototype after the source study. OpenHands SL-GCN,
training-matched input handling, a local Qwen sentence model, and explicit approval
now run in a small browser diagnostic. Replay yielded 8/11 selected dataset matches
and 0/7 recorded intended-hello matches. Sentence generation worked for a bounded
appointment request with an explicit purpose, but changed the meaning of a
requested-day example. Recognition is not ready for the intended seated setup.
See the [commands, measured results, and limitations](../../spikes/recognition/README.md).
No new live footage, training, cloud inference, speech-provider output, or call
integration was tested.

Follow-up testing used the user's open Helium browser and the real preview URL.
All 18 saved clips reproduced those recognition results with cached landmarks.
Nineteen backend tests and sixteen browser assertions pass. The check exposed and
fixed stale draft text remaining visible after a failed request; the today
sentence-meaning error remains. See the spike README for the reproducible browser
check and its limitations.

## Recognition update — 20 October 2026

The [ISL recognition landscape](../research/recognition/landscape.md) studies
the user's Hugging Face/Kaggle leads, relevant papers, and the techniques behind
them. The [source audit](../research/recognition/source-audit.md) records
artifact revisions, exact label inventories, evaluation limits, and data terms.
This source-based study supersedes the earlier default ordering of model trials.

INCLUDE now runs in the local diagnostic harness. Recorded results are 10/11
selected dataset clips and no hello predictions from seven intended-hello webcam
segments. Tests are paused. Framing is a hypothesis, not a proven root cause;
those reused recordings are development evidence. No candidate is approved for
the demo, and the call-audio gate remains separate.

## Current recommendation and scope — 19 October 2026

**Recognition handoff and recorded results:** [validate AI4Bharat INCLUDE pretrained inference](2026-10-20-include-validation.md), with the earlier [reuse-options audit](../research/recognition/reuse-options.md). The 20 October update above governs current recognition status.

**Meaningful Bolna integration is mandatory by the user's latest instruction.** The user still prefers ordinary own-number Phone calling, and now explicitly permits researching deviations when needed. The immediate authorized work is a Bolna backend feasibility prototype; the polished app UX and sign-recognition implementation are deferred until its backend checkpoint. The earlier blanket prohibition on evaluating service-originated/app-owned calls or delegation is superseded. Researching a pivot does not approve its architecture.

Read the [new product-directions report](../research/product-directions.md) first. The primary bet is one user-controlled administrative appointment conversation, demonstrated seated with a propped iPhone, a changed offer and real repair. Preserve native calling if a substantive Bolna/device proof works; otherwise make an explicit app-owned Bolna-call pivot for the same task. Supervised errands and a face-to-face counter exchange are compared alternatives, not additional promised modes. Pickup coordination has strong specific problem evidence but more difficult outdoor signing posture.

Pinned OSS source now establishes an engineerable **text-input/audio-output Bolna transport with marks and clear messages**. Inspected routing/lifecycle defects mean it is not configuration-only or runtime-validated. The older hosted standalone-TTS not-found result remains valid for those checked hosted docs; it does not rule out source integration. Current research proposes two decisive engineering experiments for a future authorized build phase, rather than asking the founder to solve the integration.

The [earlier feasibility report](2026-10-18-feasibility.md), [claim ledger](../CLAIM-LEDGER.md), [workflow](2026-10-28-workflow.md) and [validation plan](../../PLAN.md) preserve dated findings. Their hard no-pivot scope, optional-Bolna wording and unknown mandatory-use statements are historical and superseded by this notice and the new report. Platform audio boundaries and unexecuted empirical gates still apply. Impact/seamlessness are the user's working product criteria; no official judging weights or winning probability were established.

## Corrections that govern the next phase

**Preferred native path:** the user calls normally, from their own existing number, through Phone/Contacts and Ishara mediates that existing call. A verified Bolna test destination is not required for this path. Any selected service-originated alternative must disclose changed caller identity/workflow and meet its own account/telephony requirements; it cannot be described as the same native call. No actual call has been placed.

Apple publicly documents AAC app-speech injection into calls, so rejecting all ordinary-call augmentation was too broad. Equally, no supported app-readable incoming Phone audio/transcript was established: **user-visible system captions do not give Ishara a transcript**. A decision model cannot know the receptionist's question, offered time or booking outcome from an unseen caption overlay. Native Phone mute mutes injection too; room-microphone ducking is not promised by the consulted docs.

Jev now has experimental image input; an indexed text-only description is stale. The specific Laya MLX port is Mac/Python, but a separate Laya ANE/Core ML iOS implementation candidate exists. Neither establishes ISL accuracy or iPhone latency. Phrase/sentence ISL datasets exist; isolated-word accuracy is not evidence for continuous conversation. The inherited 26-word 62%/83% result has no reviewed artifact.

Bolna Custom TTS's `/audio/speech` is a developer-supplied upstream endpoint, not a standalone hosted Bolna synthesis API. No standalone hosted arbitrary-text synthesis endpoint was established in the checked public docs; the current pinned OSS route is a distinct engineering option. The official buildathon page establishes a voice component and 31 October 2026 submission date. Meaningful Bolna is mandatory by user instruction; hosted-only versus OSS eligibility, judging rubric, submission details and exact timezone remain unestablished.

## Executive finding

The preferred **unvalidated** native candidate is normal Phone call → foreground Ishara camera → supported recognized intent/approved content → Bolna OSS speech orchestration → Apple's AAC injection, with system Live Captions read by the user and native controls ending the call. One-time permissions/settings and an explicit Open Ishara step are expected; automatic background camera takeover is not established. A local-TTS-only prototype would isolate Apple routing but would not itself satisfy mandatory meaningful Bolna integration.

The iPhone 17 is confirmed, installed iOS is not. The current consulted Apple feature list is for iOS 27; English (India) captions do not mean Hindi-to-English translation. Combined camera, AAC and caption behavior must pass a physical-device gate before architecture is committed. Native-language scope and bounded natural-phrase coverage are central product decisions.

## Research map

| Artifact | Purpose |
|---|---|
| [Current product-directions report](../research/product-directions.md) | Primary appointment-call bet, four concrete directions, meaningful Bolna paths, explicit pivots, two decisive experiments and subsequent design work |
| [Everyday workflow/product note](../research/everyday-workflows.md) | Primary Indian DHH research, existing VRS/text options, concrete tasks, agency and physical signing posture |
| [Bolna integration-path note](../research/speech-device/bolna-paths.md) | Pinned OSS input/output/lifecycle findings, hosted tools/events and exact supported-versus-engineerable boundaries |
| [Demo/recognition feasibility note](../research/speech-device/demo-feasibility.md) | Checkpoint/label-map audit, model/data limits, changed-offer repair demonstration and evidence priorities |
| [Narrative feasibility report](2026-10-18-feasibility.md) | Recommendation, rationale, alternatives, engineering gaps and founder questions |
| [Working workflow](2026-10-28-workflow.md) | Provisional persona, existing-call steps, added friction, user-owned decisions, conceptual data flow and repair |
| [Validation plan](../../PLAN.md) | Ordered device/data/model/provider gates, measurements and decision implications; none of the future experiments executed |
| [Claim ledger and complete source inventory](../CLAIM-LEDGER.md) | Stable claim IDs, exact URLs, evidence limits, source conflicts and every external URL retained from the topic notes |
| [iOS and workflow note](../research/speech-device/ios-and-workflow.md) | AAC, Phone ownership, captions/translation, camera/Dynamic Island, device and future face-to-face ASR constraints |
| [Bolna and calls note](../research/speech-device/bolna-and-calls.md) | Non-telephony qualification, three redacted read-only checks, competition facts; archived service-call findings explicitly superseded |
| [Recognition and models note](2026-10-18-recognition-notes.md) | Data/license distinctions, temporal/phrase recognition, Jev/Laya/Google limits, historical 27-item inventory and evaluation design |
| [Project plan](../../PLAN.md) | Completed source research and remaining gates; requirements → architecture → tickets → build are not started |

## Evidence date and meaning

Sources checked **18 October 2026**; current synthesis/navigation updated **19 October**. Context7 was used first for relevant documentation and Exa for source discovery/fetching, followed by primary source/code inspection; current primary pages take precedence when indexed docs conflict. Search snippets, available code, hardware specifications and author benchmarks do not establish runtime success. No large dataset/model download, training, inference, installation, app implementation, call or deployment occurred in this research. The older consolidated ledger inventories the initial feasibility round; new product-direction citations are retained in the new report and its three topic notes.

The ledger uses **VERIFIED** for specifically described source/metadata facts or the three actual read-only account observations; **DOCS-ONLY** for documented behavior not executed here; **REPORTED** for author experiments not reproduced; **UNVERIFIED** for inherited results and engineering hypotheses; and **CONTRADICTED** for precise older claims refuted by current sources or explicit requirements. None of these labels implies end-to-end user validation.

No Deaf participant validation is available. Online sources and signer/session-held-out evaluation can inform and constrain the prototype, but cannot establish community acceptance, natural signing or caption suitability. Secrets remain outside the repository; account responses are not retained. Public URLs and safe aggregate API observations are the only account-related evidence recorded here.

## Next boundary

Current source research is complete enough to guide the authorized backend prototype, not to promise feasibility. Follow the revised [immediate plan](2026-10-20-plan.md#immediate-plan-bolna-call-path-backend-prototype): prove text-to-audio/session control first, then use only a minimal diagnostic device harness to test Apple's AAC path on an existing call. Any cellular test uses the user's line, synthetic content and a consenting recipient; no Bolna-originated call. Full requirements, architecture and tickets for the app follow the backend checkpoint.
