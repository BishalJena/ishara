# Ishara feasibility validation plan

> Historical experiment design, not current authorization or status. The
> [active plan](../../PLAN.md) owns current tasks and acceptance gates.

Status: proposed experiments, **none executed**, except the explicitly listed read-only Bolna checks. Research date: 18 October 2026. No product code, installation, outbound call, billable inference or deployment is authorized by this document. The purpose is to determine which requirements and architecture are justified next.

**Invariant:** the user places an ordinary cellular call from their own existing number through Phone/Contacts. Ishara mediates that existing call. No Bolna-originated PSTN, callback, calling Bolna first or second-call bridge qualifies as passing a gate.

## Evidence already obtained

| Check | Actual result | What it does not prove |
|---|---|---|
| Public documentation research | Sources and contradictions recorded in [claim ledger](../CLAIM-LEDGER.md) | Runtime coexistence, latency, recognition quality or usability |
| Authenticated `GET /user/me` | HTTP 200; auth works; concurrency max 2/current 0; balance field exists, value not retained | Credit sufficiency, telephony eligibility, SDK enablement, synthesis |
| `GET /api/v1/voice-config/tts?language=en` | HTTP 200; 16 provider entries / 29 model entries | Every entry supports English or actual synthesis quality/cost |
| `GET /api/v1/voice-config/tts?language=hi` | HTTP 200; 16 provider entries / 29 model entries | Hindi synthesis, recognition or code-switching quality |

Exactly three authenticated requests were executed. No key, account ID, email, phone number or raw account response belongs in repository documents. See [Bolna note](../research/speech-device/bolna-and-calls.md) for scope.

## Gate A: prove native call composition before choosing architecture

Prerequisites are separate authorization for a physical-device spike and an actual outbound call, a consenting teammate recipient, synthetic appointment details, an agreed recording preference and a bounded test duration. **A verified Bolna destination is not a prerequisite.** The recipient is needed to verify what the other end hears, not to route the call through Bolna.

| Order | Experiment | Record | Pass/fail implication |
|---|---|---|---|
| A0 | Inspect iPhone 17 installed iOS/build, region/languages, carrier, route, AAC settings, camera permission, caption locales/assets and privacy mode | Exact configuration and available controls; no private identifiers | Compare installed features to the actual requirement before recommending an OS update |
| A1 | Place the ordinary Phone call and inject approved harmless fixed local speech using Apple's supported mechanism | Normal origin/recipient experience; remote audibility and exact phrase; injection availability; setup prompts | If speech does not reach the recipient on the supported configuration, do not commit to this architecture; investigate the platform failure explicitly |
| A2 | Add foreground camera-only preview/capture to A1 | Camera frames/interruptions, audio-session behavior, remote speech continuity | If camera and injection cannot coexist, the intended signing workflow has not passed |
| A3 | Add supported system Live Captions while Ishara stays foreground | Remote speech captions, overlay placement, delay/readability, orientation, whether own injected speech is captioned | Visible usable captions plus capture/injection are required for the candidate return path; no app-readable transcript is inferred |
| A4 | Repeat with sustained signing/inference workload once separately authorized | Observation continuity, thermal state, battery/memory, speech delay and skipped/duplicate output | Fixed-utterance success alone does not prove sustained operation |

A0 must verify **English transcription versus translation**. Test the required receptionist speech language and user's chosen readable language, including accent, dates, names, numbers and mixed speech. The current iOS 27 web list is not proof of installed support. Hindi-to-English Phone translation and a translated overlay over Ishara are unestablished; if essential and unavailable, record an unmet requirement rather than substituting a provider-originated call.

For A1–A4, deliberately exercise native mute/unmute (documented to mute injection too), quiet/noisy room, earpiece/speaker/Bluetooth routes, remote interruption, hold/resume where available, permission UI, app switching, screen lock/unlock, another camera client, call end and a subsequent new call. Check room-microphone audibility during injection; the docs do not promise ducking. Verify an Ishara Stop action stops capture/output without being labeled native hangup. Native Phone hangup must clear pending output and prevent stale speech in the next session.

Record correct/incorrect/inaudible phrase counts and denominators, duplicates, lost turns, interruption recovery and caption delay/readability observations. Capture device configuration with each result. Do not claim broad device compatibility from one setup or Deaf usability from teammate observations. Agree numeric acceptance targets before the experiment; none has been validated or invented here.

## Gate B: establish dialogue and data coverage

Start with a full appointment exchange: inquiry, offered alternatives, deliberate acceptance/rejection, identity/details, clarification, waiting, unsupported requests, user-confirmed outcome and end of call. Audit which turns use observed signing, approved pre-call information or explicit user selection. The app cannot use the unseen receptionist transcript to fill gaps.

Build a source manifest for each proposed sign/phrase: exact semantic intent and regional variant, clip source, data versus code license, redistribution restrictions, clip count, signer/session identities where available, camera orientation/mirroring, preprocessing and usable evaluation split. Audit the historical inventory rather than freeze 25 labels. Phrase/sentence datasets exist; inspect exact coverage and terms before deciding they are appropriate.

Pass evidence is a dialogue coverage map with usable licensed examples and an honest held-out protocol, including defined unsupported turns. If continuous phrase coverage is absent, compare available approaches and explicitly decide whether a separated-sign demo is acceptable. Synthetic concatenation of isolated clips does not prove natural transitions or ISL grammar. No fluent participant/expert is available, so semantic/naturalness confidence remains limited even when dataset labels are present.

## Gate C: compare recognition and decision approaches fairly

| Variant | Question | Controlled inputs |
|---|---|---|
| Temporal specialist + rules/templates | Can the simplest supported baseline emit faithful content? | Same clips, inventory, boundaries, unknown policy and approved outputs |
| Whole-phrase temporal recognition/retrieval, if data qualifies | Can bounded natural phrases reduce imposed sign-by-sign interaction? | Suitable phrase corpus, held-out protocol and comparable meanings |
| Baseline + Jev text or Laya decisions | Do available user-sign history and explicit scenario improve decisions? | No remote Phone transcript; retain visual evidence and context-conflict cases |
| Baseline + Jev visual candidate verification | Do reference examples and sampled frames reduce actual errors? | Same uncertain cohort, version pinned, disjoint references/test signers, none-of-these option |
| Jev bounded image-only comparator, optional | Is direct finite visual classification competitive? | Same held-out clips/frames, unknown examples and version |
| Laya Core ML / laya-ANE device qualification, optional | Does the candidate run with adequate parity/resources on iPhone? | Real trained conversion, not dummy bundles; token limits and preprocessing controlled |

Use true held-out signers where metadata allows, plus held-out sessions/source video. If signer identity is unavailable or approximated, label it explicitly. Keep demo-user calibration separate from final evaluation. Include idle/no-sign, unseen/unknown signs, partial phrases, continuous transitions, repetitions, body/head grammar, self-corrections, camera adjustment, occlusion and poor framing. Include context that encourages the wrong decision, and assess whether reranking confidently overrides correct visual evidence.

Measure per-class top-one/top-k and candidate recall separately from reranking; unknown false acceptance/rejection; boundary onset/end errors; duplicate speech; **wrong automatically spoken utterances per committed utterance**, including absolute counts; confirmations/re-signs per turn; and supported task outcome with user-confirmed details. A top-three score does not measure safely spoken sentences. Do not multiply model probabilities as if independent or treat Jev confidence as measured correctness.

Measure signer-finish → committed content → first remote-audible speech at p50/p95, including commitment buffer, model verification, network and TTS/injection. Record cold/warm start, frame rate, memory, temperature and battery during a representative sustained session. Report Mac benchmarks only as author-reported Mac results. Thresholds should be chosen on development examples, frozen, then assessed on the final held-out test with sample-size limitations.

Pass evidence is less wrong speech or less repair burden at acceptable measured end-to-end latency, rather than a larger confidence number. If added decision models fail to improve those outcomes, retain the simpler baseline. If unknown/idle input produces speech or ordinary nods become consent, automatic commitment has not passed.

## Gate D: qualify Bolna independently without changing calling

Ask the vendor for a supported standalone HTTP/streamed text-to-audio interface, exact formats, account flags and price, or a receive-only non-PSTN transport. The inspected Custom TTS `/audio/speech` belongs to the developer's upstream server; voice catalogs do not qualify. Obtain exact text-trigger/audio-output contracts before any billable session or integration.

If a non-PSTN WebRTC audio source is proposed, prove microphone/session coexistence with Phone, supported audio extraction and AAC routing, exact content, cancellation/deduplication, lifetime and native-call continuity. A browser session working alone fails this gate. If an agent session is deliberately selected, inspect actual timers and test 10/30/60-second signing pauses, events during recipient speech/playback/generation, repeated events and stale session state. These are conditional provider tests, not requirements to originate a telephone call through Bolna.

If no appropriate supported Bolna component exists, document the integration gap and confirm competition rules; do not force a vendor-shaped architecture. Local AAC speech remains the first platform experiment. No arbitrary-text synthesis, WebRTC enablement or paid inference has been executed.

## Gate E: agree demo scope, then define requirements

Confirm organizer rules: mandatory Bolna use or minimum integration, submission assets, judging rubric and deadline timezone. The official page establishes a voice component and 31 October submission date, not the remaining conditions.

Resolve [founder questions](2026-10-18-feasibility.md#unresolved-founder-questions) using device/data findings: return language, per-call navigation, posture, correction tradeoffs, phrase boundaries, cloud-frame consent, supported booking outcome and distribution route. Only then write requirements with measurable acceptance criteria, choose architecture/interfaces, and break work into assignable tickets. A failed gate is evidence for a scope discussion, not permission to discard the ordinary-call requirement.
