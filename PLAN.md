# Ishara project plan

Updated 19 October 2026; source notes checked 18 October. **Immediate phase: backend feasibility prototype for Bolna's role in the call flow.** Meaningful Bolna integration is mandatory by user instruction. The ordinary own-number Phone call remains the target; do not route the user's call through Bolna or have Bolna place a second call. Build the backend/process-flow proof before product app UX.


## Parallel teammate task: validate pretrained recognition

The user has requested an independent validation of AI4Bharat INCLUDE, without
training from scratch. Follow [the validation handoff](docs/tasks/validate-include-recognizer.md).
Start with the published large-transformer checkpoint, record real clip predictions
and timing, and return a go/no-go recommendation. This does not pass the Bolna/device
gate or authorize claiming continuous signing works. See the
[reuse-options audit](<docs/research_notes/Ishara hackathon product directions/recognizer-reuse-options.md>)
for pretrained alternatives, Jev and Laya.

## Immediate plan: Bolna call-path backend prototype

**Question to answer:** can Ishara send one user-approved utterance through Bolna, receive controllable speech audio, and make that audio available to Apple's supported injection path for the user's existing Phone call?

This is a backend feasibility spike, not a sign-recognition model or polished mobile application. Begin with synthetic, approved text provided through a CLI/test harness. Keep the process flow visible: approved text → Bolna session/transport → speech audio and playback markers → cancellation/session end. Do not feed unseen receptionist audio or allow the model to invent or accept appointment details.

### Ordered tasks

1. **Pin and isolate the Bolna path.** Record the upstream commit/license, required services and configuration; reproduce the source-level text-routing and synthesis behavior in an isolated development setup. Keep credentials in local environment variables and out of the repo.
2. **Build the smallest text-to-audio adapter.** Send a fixed, user-approved utterance over Bolna's supported/engineered text path, receive audio and playback acknowledgments, and support clear/cancel/end so stale speech cannot leak into another turn. Avoid speech interpretation or a general-purpose agent in this slice.
3. **Measure the backend flow.** Repeat an ordinary utterance, a long pause, cancellation during generation/playback, and a second utterance. Record exact text, audio format, time to first and complete audio, cancellation behavior, errors, and any Bolna/provider cost. A catalog response or local speaker playback alone is not a passing call-path result.
4. **Check call compatibility with a diagnostic device harness.** Once backend output is reliable, use a minimal trigger on the iPhone to pass the returned audio to Apple's AAC injection mechanism during the user's normal own-number call. This harness may expose permission/status and a test button only; defer product navigation, visual design, sign recognition, and dynamic island work.
5. **Decide the product route.** Preserve native calling only if Bolna speech, camera capture, and the user's return-caption setup can coexist. If a required part fails, document a user-visible app-owned-call alternative and its caller-ID/workflow change before selecting it.

### Acceptance evidence

- Bolna receives exactly the submitted approved utterance; audio output is captured/played and its encoding is known.
- Cancel/clear stops pending output; repeated turns do not duplicate or leak speech.
- Backend session failure and unavailable/disabled Bolna service fail closed without emitting guessed content.
- The device gate records whether the recipient hears the exact speech in the existing Phone call. No Bolna-originated call or second-call bridge counts as passing.
- Findings include source commit, reproducible setup, latency/error observations and costs. No accuracy claim is made for synthetic text or a hearing participant.

### Checkpoint before app UX

Review the backend sequence, measured results and pivot consequences. Then write the bounded conversation/repair requirements, decide recognizer ownership and caption language, and design the app workflow. The founder's coding pause was lifted for this backend prototype only; app UX and broader implementation remain deferred until this checkpoint.

**Call test boundary:** no real external call has been placed. The user has authorized the prototype; an actual cellular test must use the user's ordinary line and a consenting recipient, with synthetic content. Never originate a Bolna call to demonstrate the target workflow.

## Current product direction

- [x] Compare everyday access barriers, existing alternatives and physical signing workflow in the [everyday-workflows note](<docs/research_notes/Ishara hackathon product directions/everyday-workflows.md>).
- [x] Inspect supported hosted interfaces and pinned OSS text/audio transport in the [Bolna paths note](<docs/research_notes/Ishara hackathon product directions/bolna-paths.md>); real source primitives exist, with routing/lifecycle defects still unexecuted.
- [x] Audit available recognition starting points and propose a complete changed-offer/repair demonstration in the [demo-feasibility note](<docs/research_notes/Ishara hackathon product directions/demo-feasibility.md>).
- [x] Synthesize a [product recommendation and four directions](<docs/reports/Ishara hackathon product directions.md>): first demonstrate a user-controlled seated appointment call; preserve native own-number flow if meaningful Bolna/device proof works; otherwise explicitly evaluate app-owned calling for the same user-led task.
- [ ] Complete the immediate Bolna backend prototype and device gate above before starting app UX.
- [ ] After the backend checkpoint, run blinded bounded recognition/conversation with a changed offer and repair; source research did not validate model performance.
- [ ] Turn the results into one conversation/repair map, source-qualified phrase/data manifest, supported spoken/readable languages and transport decision. The team owns this technical investigation; do not ask the founder to solve integration details.
- [ ] Clarify hosted-only versus OSS integration eligibility, submission assets and exact deadline timezone. Mandatory meaningful Bolna is settled by the user, not an open product question.

## Earlier feasibility research — retained background

## Research

- [x] Capture the earlier hard native-call requirement. **Updated:** ordinary Phone/Contacts calling is still preferred; latest user permission allows researching clearly disclosed app-owned calling or delegation pivots.
- [x] Research public [iOS/call/camera/caption capabilities](<docs/research_notes/Ishara feasibility research/ios-and-workflow.md>) and distinguish user-visible captions from app-readable transcripts.
- [x] Research [Bolna non-telephony fit and buildathon constraints](<docs/research_notes/Ishara feasibility research/bolna-and-calls.md>); complete only three read-only auth/catalog checks.
- [x] Research [ISL data, model choices, licensing and historical vocabulary](<docs/research_notes/Ishara feasibility research/recognition-and-models.md>), without claiming model performance was reproduced.
- [x] Consolidate [research entrypoint](docs/RESEARCH.md), [narrative report](<docs/reports/Ishara feasibility research.md>), [claim/source ledger](docs/CLAIM-LEDGER.md), [provisional workflow](docs/WORKFLOW.md) and [validation plan](docs/VALIDATION-PLAN.md).
- [ ] Inspect actual iPhone 17 iOS/build/settings and required caption language; do not prescribe an update without that evidence.
- [ ] If native calling remains the selected experiment, after separate authorization prove actual Bolna speech + AAC + foreground camera + system captions concurrently with a consenting recipient. No Bolna number verification is required for that native path; an explicitly selected service-originated experiment has separate operational requirements.
- [ ] Audit dialogue coverage, exact licensed sign/phrase assets, signer/session splits, unknown handling and language/grammar limitations.
- [ ] Agree acceptance measures, then compare baseline recognition/templates with optional decision/visual verification models on held-out and continuous/idle inputs.
- [ ] Qualify the source/hosted path in the current product report; do not interpret the earlier hosted standalone-TTS not-found result as excluding OSS engineering.
- [ ] Resolve remaining language/workflow choices using evidence; [earlier questions](<docs/reports/Ishara feasibility research.md#unresolved-founder-questions>) are background, superseded where the current report settles direction or user instruction. No Deaf participant validation is available.

## Subsequent stages — not started

1. **Requirements:** persona assumptions, supported conversation, accessibility/privacy behavior, failure/repair, acceptance criteria and explicit exclusions.
2. **Architecture:** choose components, device/session ownership, interfaces and state based on passed gates; record remaining risks and decisions.
3. **Delivery planning:** milestones and assignable tickets with dependencies, acceptance criteria and verification, sized for the team and confirmed hackathon constraints.
4. **Build:** implement only after the user requests it, then verify the actual supported experience.

No code, installations, actual test calls, paid inference or deployments are authorized by this research plan.
