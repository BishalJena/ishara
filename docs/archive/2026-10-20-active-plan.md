# Active plan (archived)

> Superseded on 23 October 2026 by the demo build plan in [PLAN.md](../../PLAN.md).
> The recognition acceptance gate and pilot protocol below are still referenced by it.

Updated 20 October 2026. This file owns active tasks and acceptance criteria.
Read the [handoff](2026-10-28-handoff.md) for current capability, the
[experiment record](../experiments/recognition.md) for measurements, and the
[archive](README.md) for completed investigations.

## Recognition: fresh-data pilot

Goal: one seated signer intentionally produces a complete supported sign, gets a
correct concept or an unsure result, and can approve a sentence preserving the
explicit meaning. SignCLIP is the leading representation; SL-GCN is the comparison.

Vocabulary: **hello, thankyou, doctor, hospital, tomorrow**. Use explicit clip
boundaries. This is personalized isolated-sign recognition, not unrestricted
translation or sign spotting within continuous signing.

- [ ] Capture 3–5 complete takes per concept in one enrollment session. Preserve
  raw video, timestamps, camera configuration and a consistent session ID.
- [ ] Review tracking overlays and verify sign forms with appropriate ISL
  expertise/reference material. Human verification notes are required; good
  tracking alone does not establish correct signing.
- [ ] Collect a different calibration session: at least 5 supported attempts per
  concept and 20 negatives spanning idle, transitions, incomplete and unsupported
  signs. Do not reuse enrollment or test sources.
- [ ] Compare both encoders on those same development inputs. Calibrate rejection
  using development data only; retain at least 60% correct accepts per concept
  without wrong accepts. Reject-all cannot qualify.
- [ ] Choose the encoder and freeze its thresholds and development fingerprint
  before inspecting the final test.
- [ ] Collect a different final session: at least 10 attempts per concept and
  50 negatives across the same four negative categories. Evaluate once the labels
  and capture quality have been reviewed.
- [ ] Measure sign completion to visible prediction with fresh extraction in the
  actual capture flow. Diagnose extraction cost; cached or batch timings cannot
  substitute for this measurement.
- [ ] Connect the selected calibrated recognizer to the existing composition and
  approval boundary only after the pilot supports it.

Start with the 15 enrollment clips. The [capture runbook](../../spikes/recognition/README.md#capture-and-review)
has the command and controls. Actual camera keyboard operation awaits this session.

### Recognition acceptance gate

- At least 90% correctly accepted attempts for **each** concept (at least 9/10).
- Zero wrong accepted labels among supported-sign attempts.
- Zero accepted labels across at least 50 held-out negative clips.
- Under two seconds from sign completion to visible prediction, including fresh
  extraction; record hardware, camera and processing configuration.
- Sentence fixtures preserve explicit intent, day and subject. Editing and
  single-use approval remain exact; abstention cannot feed composition.

If a final test informs changes, retire it as development evidence and collect a
new final test session. If reference matching cannot separate the concepts, inspect
tracking/sign variation before choosing limited adaptation and more development
data. Do not train merely to improve the seven old intended-hello clips.

## Speech: establish meaningful Bolna output

This track can progress independently of recognition, using approved synthetic
text and the [call-flow runbook](spikes/call_flow/README.md).

- [ ] Establish a usable Bolna text/audio integration. Inspect the OSS routing and
  lifecycle issues identified in [the source study](../research/speech-device/bolna-paths.md);
  a successful account or catalog request is not speech synthesis.
- [ ] Produce genuine audio for exactly the approved text; record format, sample
  rate, first-audio/completion timing and provider configuration.
- [ ] Exercise cancellation, duplicate/late results, new sessions and output
  failures. Old or unapproved utterances must not play.
- [ ] Confirm which Bolna integration and submission assets satisfy the organizer's
  rules. Mandatory Bolna use is already a product requirement; hosted-only versus
  OSS eligibility and the judging rubric remain unestablished.

Pass requires actual provider audio and controllable output, not mock events or
Apple local speech. No target call may be routed through Bolna or duplicated.
Calls, paid inference, installations and deployment need task authorization.

## Device: verify the recipient's experience

- [ ] Record the iPhone's installed iOS, available AAC/caption settings, camera
  permissions, caption language and audio route; install the diagnostic harness.
- [ ] Use a user-started call and a consenting recipient to verify exact approved
  speech is heard. An Apple-voice control isolates platform behavior; repeat with
  genuine Bolna audio before claiming the integration works.
- [ ] Verify Stop, interruptions, quiet signing pauses, mute, route changes,
  app switching, call end and a subsequent call. Prevent stale playback.
- [ ] Test foreground camera, speech injection and readable system captions
  together. WhatsApp voice-call success does not establish carrier Phone behavior;
  the ordinary Phone call needs its own test.
- [ ] Record remote audibility and exactness, duplicates/dropped output, caption
  readability and timing. Observe the full flow rather than relying on local
  playback or an injection-availability indicator.

System captions remain user-visible, not an app-readable transcript. Native call
controls own hangup. Camera capture in the background is not assumed.

## Checkpoint before polished app UX

Proceed only when the bounded recognition, approved speech and intended device
composition have supporting evidence. If native calling fails, explicitly decide
whether an app-owned/service-originated route is an acceptable product pivot.

A small personalized pilot does not establish general ISL reliability, natural
conversation or accessibility validation. No Deaf participant study has occurred;
the [workflow](2026-10-28-workflow.md) keeps those limits explicit.
