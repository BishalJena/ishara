# Recognition experiment record

Executed 20 October 2026 on the development Mac. This is the authoritative summary
of local ML measurements. [Runbook](../../spikes/recognition/README.md) ·
[Current direction](../archive/2026-10-28-handoff.md) · [Next acceptance gates](../../PLAN.md)

Later, separate run: [video-to-voice pipeline on public ISL videos](../archive/experiments/video-pipeline-eval.md)
(24 October, cross-signer, through the live recognizer, composer and voice).

## Scope

The corpus contains 11 selected public INCLUDE clips and seven saved
intended-hello webcam segments from two earlier sessions. These are development
examples, not a fresh held-out pilot. The webcam meanings were intended by the
signer, without independent ISL verification. No Deaf participant validation,
training, natural-conversation evaluation or phone inference occurred.

Private footage and generated reports remain in ignored `spikes/recognition/artifacts/`
(paths below are relative to that spike). A fresh checkout can fetch public examples
but cannot reproduce private-footage counts without those recordings. The detailed
historical notebook is [archived here](../archive/2026-10-20-recognition-notes.md).

## Original INCLUDE transformer

The 263-class transformer matched **10/11 public clips**. Doctor ranked slow
first (0.47 versus doctor 0.43); the other selected clips matched. Its forward pass
took approximately 10 ms per clip; landmark extraction was about 30 ms per
1080p frame in that diagnostic.

None of the seven intended-hello webcam segments produced hello. Initial wrong
labels included warm, orange, author and queen. The verdict remained undecided.
Framing, sign variation, tracking, preprocessing and temporal handling were not
isolated as causes. There is no established requirement that the user stand back.

The port fixes upstream's unconditional inference dropout. Its 134-coordinate
input uses 25 pose points and both hands, interpolates missing coordinates,
scales to 1920×1080 and pads/truncates to 169 frames. The live segmenter and
normalization experiments are local diagnostic additions, not proof of exact
upstream reproduction. [Original task/results](../archive/2026-10-20-include-validation.md)
and [camera observations](../archive/2026-10-20-plan.md) preserve the details.

## SL-GCN classifier and initial sentence prototype

With its own 27-joint preprocessing and class order, the 263-class SL-GCN matched
**8/11 public clips and 0/7 intended-hello clips**. All seven webcam attempts
abstained because their winners were outside the supported subset.

Both location clips became Photograph (0.767 and 0.908); today became they
(0.993). Doctor matched at 0.999 and tomorrow at 0.591. Two constructed negatives
(black video and a repeated reference frame) abstained. They do not replace
real idle/transition/unsupported clips or establish general unknown rejection.

Median model/transform time was about 20.1 ms; original whole-clip extraction
median was about 4.23 s. Later cached replays disclose their cache status.
The original report is `artifacts/mini/evaluation.json`.

Qwen generated an appointment request from doctor + tomorrow with explicit
appointment purpose, but changed today + requested-day purpose into
“Hello, what day is today?” Missing intent was blocked. Fluency did not guarantee
semantic preservation.

Browser checks also exposed stale draft text after a failed request. The UI now
clears the old sentence and provenance; the backend rejects stale approvals.

## Frozen reference matching

Both encoders used the same five concepts and eight public in-scope references.
Lookup excludes the query's ID, source ID and content hash. Query labels affect
scoring only.

- **Seven intended-hello recordings:** SignCLIP ranked hello first on **7/7**;
  SL-GCN features did so on **0/7**.
- **Six scorable public queries:** SignCLIP **5/6**, SL-GCN features **6/6**.
  SignCLIP's incorrect public hello query ranked tomorrow first.
- Doctor and tomorrow each have only one reference; their public clips cannot
  score themselves. Three public clips are outside the five-concept vocabulary.
- An out-of-scope today clip matched hello at **0.931 cosine similarity**, above
  all seven intended-hello matches (**0.532–0.590**).

Every retrieval replay **abstains**. Similarities and margins are diagnostic,
not calibrated probabilities or accepted concepts. This five-concept retrieval
task is different from the original 263-class classification tasks.

Median embedding time was about **54 ms SignCLIP / 20 ms SL-GCN** on CPU with
four PyTorch threads. Original whole-clip landmark extraction medians:

- Public clips: **1.59 s SignCLIP / 3.72 s SL-GCN**.
- Webcam clips: **2.93 s SignCLIP / 7.08 s SL-GCN**, with 47–169 frames per clip.

These batch observations exclude the full capture-to-display path and do not
pass the live two-second gate. Evidence:
`artifacts/retrieval/replay-{signclip,slgcn}.json`.

SignCLIP loaded all 205 video state entries strictly. An obsolete positional-ID
buffer was checked against its deterministic replacement before exclusion. A real
63-frame clip produced a finite 768-value embedding with repeat maximum difference
zero. The unused text encoder and optimizer were not instantiated.

## Current composition and tooling verification

Fixed templates now produce “I would like an appointment with a doctor tomorrow.”
from doctor + tomorrow and appointment intent, and “I would like today.” from
today and requested-day intent. Conflicting days and incompatible concepts block
drafting. Exact editing and one-use approval remain required; speech is unconnected.

The real public doctor/tomorrow → SL-GCN prediction → template → edited approval
path passed in Helium. **34 backend/data tests and 20 browser assertions passed.**
The browser suite deliberately provokes two HTTP 400 resource errors. Template
evidence is separate: `artifacts/mini/evaluation-templates.json`.

Capture MP4 round-trip and manifest safety checks pass. A full 63-frame public
hello tracking overlay was rendered and visually inspected; it is tooling smoke
evidence outside the real pilot dataset. No new pilot recordings or human-verified
labels exist, and actual keyboard-driven camera capture remains to be exercised.

A clean tracked-file export also passed the backend/data commands with one
OpenHands transform test skipped because its source checkout was absent. It reused
the installed Python environment; it was not a fresh dependency installation.
The separate [call-flow runbook](../archive/spikes/call_flow/README.md) owns its mock,
provider-probe and iPhone build observations.

## Artifact provenance

- INCLUDE source: `df348f4a640060d4d39f02556d9f96851e8c46c7`; large-checkpoint SHA-256:
  `13fc65e0a4c15baff3285b533fc90299a44546f41b548531dfe7494a636b3215`.
- OpenHands source: `b9ccf9eaf2a71301fc4601a64a6af06fdef04c9b`; checkpoint archive SHA-256:
  `0aa8eb27091dff71e5ae721a648a7410abb827c495731d3da43c55f195757a52`.
- SignCLIP source: `a819944093876443119f294a2c50c663cecd65b0`; checkpoint SHA-256:
  `a739751dd5b79a42f335725b4de4811c632f9f0cba616b74a8c8d87e55784df9`.
- Qwen revision: `7ae557604adf67be50417f59c2c2f167def9a775`.

The adapters/setup scripts pin further metadata and contracts. Local reports retain
hashes, frame counts, FPS, dimensions, tracking fractions and cache/timing status.
Requirements files specify the separate environments; their `.lock` companions
are observed local freezes, not cross-platform dependency guarantees.
