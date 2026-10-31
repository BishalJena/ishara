# Recognition diagnostics for the bounded ISL pilot

> Historical implementation notebook, including the original measurements,
> preprocessing details and old commands. Use the [current runbook](../../spikes/recognition/README.md)
> and [experiment record](../experiments/recognition.md).
> Commands below assume the `spikes/recognition` working directory, not this archive.

Runs AI4Bharat's pretrained INCLUDE Indian Sign Language model (263 isolated signs)
on the Mac against a webcam or the iPhone via Continuity Camera, and records every
captured segment so the same clips can later be replayed through other candidates.
No training. Everything under `artifacts/` (clone, weights, clips, sessions) is gitignored.

For repository context and a fresh checkout, start with the
[teammate handoff](2026-10-28-handoff.md). The adapted INCLUDE implementation
retains its upstream MIT notice in [INCLUDE-LICENSE.txt](../../spikes/recognition/INCLUDE-LICENSE.txt).

## Current checkpoint: frozen SignCLIP reference matching

**Decision:** SignCLIP is the leading representation for a fresh-data pilot.
Recognition is still unapproved for speech. There are no new user recordings or
verified pilot labels yet.

This follow-up compares **video-to-video embeddings**, not English-text prompting:
one complete clip → model-specific landmarks → frozen embedding → nearest
labeled ISL reference per concept. The vocabulary is hello, thankyou, doctor,
hospital and tomorrow. Query truth is used only for scoring, never for lookup.

### Executed development results

- Both encoders processed the same 18 saved clips and used the same eight public
  in-scope clips as references. A query cannot match its own ID, source or content
  hash. Doctor and tomorrow have only one reference each, so their public clips
  cannot be scored as queries; three public clips are outside this vocabulary.
- **Seven intended-hello recordings:** SignCLIP ranks hello first on 7/7; SL-GCN
  feature matching on 0/7. These are reused recordings from two earlier sessions,
  all intended to express one meaning. They do not establish five-sign accuracy.
- **Six scorable public queries:** SignCLIP 5/6; SL-GCN features 6/6. SignCLIP's
  incorrect public hello query ranks tomorrow first.
- **Rejection is unresolved:** an out-of-scope today clip matches hello at 0.931
  cosine similarity, above the 0.532–0.590 of the user's intended hello attempts.
  A high similarity is not a probability of correctness. Margin helps describe
  ambiguity but has not been calibrated on fresh negatives.
- **Every retrieval replay decision abstains.** Rankings are diagnostic only and
  are not connected to sentence generation or speech.
- **Timing:** median embedding inference is ~54 ms SignCLIP and ~20 ms SL-GCN,
  on CPU with four PyTorch threads. Original whole-clip landmark extraction
  medians are ~1.59 s/public clip and ~2.93 s/webcam clip for SignCLIP, versus
  ~3.72 s and ~7.08 s for SL-GCN. Webcam clips contain 47–169 frames. These are
  batch observations, not live sign-completion-to-visible-result measurements.
  The two-second target is unmet; cached extraction cannot satisfy it.

Evidence stays local in `artifacts/retrieval/replay-signclip.json` and
`replay-slgcn.json`. Each query retains its hash, extractor, frame count, FPS,
dimensions, tracking quality, cache status, top matches, margin and timing.
The selected old corpus is for development only, with no verified independent
signer evaluation or pretraining-overlap guarantee.

### Reproduce the model comparison

Use an isolated SignCLIP environment; its Transformers version differs from the
existing miniature. Assets and the environment already exist on this machine.
For a new checkout:

```sh
mkdir -p artifacts/signclip
uv venv --python 3.11 artifacts/signclip/.venv
uv pip install --python artifacts/signclip/.venv/bin/python -r requirements-signclip.txt
artifacts/signclip/.venv/bin/python setup_signclip.py
```

Setup downloads the upstream source, ~2.4 GB official multilingual checkpoint and
pinned BERT tokenizer/configuration metadata. It does not download BERT base-model
weights or send recordings anywhere. The baseline and corpus require the earlier
miniature/clip setup below. Personal recordings are deliberately not distributed.

```sh
artifacts/signclip/.venv/bin/python retrieval.py replay --encoder signclip
.venv/bin/python retrieval.py replay --encoder slgcn
.venv/bin/python -m unittest -v test_retrieval test_mini
```

The adapter uses source revision `a819944093876443119f294a2c50c663cecd65b0`,
checkpoint SHA-256
`a739751dd5b79a42f335725b4de4811c632f9f0cba616b74a8c8d87e55784df9`,
and BERT metadata revision `cd5ef92a9fb2f889e972770a36d4ed042daf221e`.
All 205 video-encoder state entries load strictly. One obsolete positional-ID
buffer is checked for equality with its deterministic replacement before removal;
no learned weights are substituted. The unused text encoder/optimizer is omitted.
A real 63-frame clip produced finite 768-dimensional embeddings with maximum
repeat difference zero.
`requirements-signclip.lock` records the observed Python 3.11.15 environment,
including transitive versions; it is a local freeze, not a cross-platform lock.

Input follows pinned upstream `demo_sign.py` pose preprocessing: pose-format 0.9.0,
MediaPipe Holistic 0.10.21 complexity 1, shoulder normalization, reduced face
contours and hidden legs, yielding 609 features per frame. Upstream inference
pads to 256 frames and masks unused frames; the local adapter calls upstream
`MMFusionSeparate.forward_video` including its pooling. Clips longer than 256
frames fail explicitly. Coordinates are extracted at native decoded dimensions
without mirroring, interpolation, sign trimming or silent truncation.
Checkpoints load with `weights_only=True`, CPU memory mapping and a narrowly
allowed inert `argparse.Namespace`; runtime resources are local-only.

### Fresh capture and label review

Start with **three complete examples of each concept** (15 total), in the seated
demo setup. Use a local pseudonym and keep the **same session ID for the entire
recording session**, even when restarting the command for another concept:

```sh
.venv/bin/python pilot_capture.py capture \
  --signer demo --session enrollment-01 --split enrollment \
  --concept hello --takes 3 --camera 0
```

Repeat for `thankyou`, `doctor`, `hospital` and `tomorrow`. SPACE starts/stops a
take; X discards it; Q/escape exits and discards any unfinished take. Keep the
face, shoulders and hands visible. Save the whole sign with brief neutral
boundaries. Long takes are rejected rather than cropped; do not rush a sign to
fit. The camera requests 1280×720 at 30 FPS; the actual frame timing/dimensions
are stored. Encoding uses the measured mean frame rate, with frame timestamps and
maximum gaps retained for diagnosing irregular capture. Memory is bounded.

Raw MP4s and `artifacts/pilot/dataset.json` stay local. Every take starts
**unverified**. The tool prints its clip ID. Review the raw signing alongside the
tracking overlay, using ISL expertise or a documented, appropriate ISL reference:

```sh
.venv/bin/python pilot_capture.py review --id CLIP_ID
.venv/bin/python pilot_capture.py verify --id CLIP_ID \
  --note "Describe the actual sign-form review and the ISL reference used"
```

`review --headless` writes the full overlay without opening a window.
Review outputs live under `artifacts/pilot/review/`. Tracking quality does not
verify linguistic meaning. `verify` records **your explicit assertion**, with a
required note; it does not automatically judge ISL correctness. Review never
displays classifier predictions, including for test clips.

MP4 encoding/decoding and manifest safety passed automated checks; a full
63-frame public hello overlay was rendered and visually inspected. Its separate
smoke manifest is under `artifacts/retrieval/`, outside the real pilot dataset.
Camera start/stop keyboard operation still needs the first new capture session.
The combined current backend suite has **34 passing tests**.

### Calibrate, freeze, then evaluate

```sh
.venv/bin/python retrieval.py status
artifacts/signclip/.venv/bin/python retrieval.py calibrate --encoder signclip
.venv/bin/python retrieval.py calibrate --encoder slgcn
# Select the encoder using development evidence before inspecting the final test.
artifacts/signclip/.venv/bin/python retrieval.py evaluate --encoder signclip --fresh
```

Coverage prerequisites:

- Enrollment: at least 3 verified examples per concept.
- A **different** calibration session: at least 5 per concept, plus 20 negatives
  spanning idle, transitions, incomplete signs and unsupported signs.
- A **different** final test session: at least 10 per concept, plus 50 negatives
  spanning those same four categories.

Use `--concept idle`, `transition`, `incomplete` or `unsupported` when capturing
negatives. These have no supported label; document what was performed in `--note`
and verify the annotation. Enrollment accepts only supported concepts.

The manifest rejects session/source/hash overlap across splits and duplicate
videos. The personalized pilot requires one designated signer. Enrollment and
calibration fingerprints and the encoder contract bind the frozen policy;
changing them requires recalibration. Calibration considers only development
embeddings and seeks zero wrong accepts while retaining at least 60% of each
concept. Reject-all cannot pass. Missing tracking and nonfinite evidence fail
closed; similarity is never described as calibrated confidence.

Final criteria are at least 90% correctly accepted per concept, zero wrong
accepted labels, and zero negative accepts. Fresh batch p95 processing is also
reported, with a two-second target. That excludes capture, ranking and display:
`live_latency_validated` and `demo_ready` remain false. A batch pass alone does
not pass the full product gate. If a final test informs a change, retire it as
development evidence and collect a new final session; do not tune on its failures.

### Default sentence path

`mini.py serve` now uses **fixed intent templates**. It retains the existing
SL-GCN diagnostic recognizer; SignCLIP ranks remain in the separate experiment
until calibration passes. Supplied concepts are still explicitly distinguished
from model predictions.

- Doctor + tomorrow + request appointment → “I would like an appointment with a
  doctor tomorrow.”
- Today + specify day → “I would like today.”
- Conflicting days, incompatible concepts or missing purpose → no draft to approve.

Exact editing, single-use approval and invalidation still apply. `--composer llm`
retains the previous optional experiment; it is not used by default.
`mini.py evaluate` saves `artifacts/mini/evaluation-templates.json`, preserving
the earlier LLM evidence in `evaluation.json`. The real public doctor/tomorrow
recognition → template → edited approval path passed in Helium, along with
**20 browser assertions** using `test_mini_browser.js`. Its two deliberate HTTP
400 cases appear as expected console resource errors. No speech or call was made.

## Earlier miniature: SL-GCN + local LLM + approval

The following records the initial LLM-default experiment. Use `--composer llm`
to reproduce that historical behavior; the current default is described above.

The user authorized this miniature on 20 October after the research pass.
It uses **real pretrained OpenHands SL-GCN** and **real local Qwen2.5-0.5B-Instruct**
generation. It replays recorded clips, preserves raw predictions, filters candidate
concepts, proposes a sentence, and records the exact text the user approves or edits.
The separate “supplied concepts” mode bypasses recognition and is labeled accordingly.
There is no trained model of our own, cloud inference, or recording upload.

**Result: the pipeline runs, but recognition is not ready for the intended setup.**
This SL-GCN configuration got 8/11 selected dataset clips right and 0/7 recorded
intended-hello segments. Those reused recordings are development evidence, not
a fresh evaluation or qualified linguistic assessment.

### Run it

From `spikes/recognition`, using the existing environment:

```sh
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python setup_mini.py
.venv/bin/python mini.py serve
```

Open `http://127.0.0.1:8088` directly. If using a local browser-preview proxy on a
different port, restart the server with that preview's exact origin:

```sh
.venv/bin/python mini.py serve --preview-origin http://127.0.0.1:64343
```

Replace `64343` with the current preview port. Without this option, the page can
load through the proxy but button actions fail with “Cross-origin requests are
not allowed.” Only the configured preview is added; other origins and hosts stay
blocked. No browser security setting needs changing.

To reproduce the measurements and contract checks:

```sh
.venv/bin/python mini.py evaluate
.venv/bin/python -m unittest -v test_mini
```

On a new checkout, create the Python 3.11 environment as below first, and run
`fetch_clips.py` for the official examples. Personal recordings remain local;
without them the replay denominator changes. `mini.py evaluate` also needs at
least one official hello clip to construct its synthetic static-frame check.

This is a single-user, single-turn diagnostic server bound to loopback, with known
local clips only. It is not a deployed API. The interface can inspect multiple
clips per turn; use Reset turn before a different utterance. No new webcam session
or continuous segmentation is implemented by this miniature.

### What ran, and what did not

- **Recognition:** 263-way SL-GCN inference; the prototype supports candidate
  concepts hello, thankyou, doctor, hospital, location, today, and tomorrow.
  It never renormalizes the classifier over only those seven labels.
- **Sentence generation:** a pinned, local 0.5B-parameter LLM. Explicit purpose is
  required for ambiguous fragments. Empty and unsupported concept lists are rejected.
- **Approval:** exact user-edited text, single-use draft IDs, and invalidation when
  recognition changes or the turn resets. Nineteen contract tests pass, including
  five HTTP checks for direct access, configured preview access, and rejection of
  unrelated origins and hosts.
- **Speech/calling:** not connected. Approval returns `sent_to_bolna: false` and
  `speech_status: not_connected`. This is a recorded boundary, not a mock claim
  that Bolna or the recipient received speech.

The real browser check combined the doctor and tomorrow dataset predictions,
selected the appointment-request purpose, generated a sentence, edited it, and
approved the exact edited text. It also verified that a failed recorded hello
cannot proceed to composition and that approval becomes unavailable after use.

### Follow-up in the user's open Helium browser

On 20 October, all 18 saved clips were selected and analyzed through the actual
preview URL. Results reproduced 8/11 dataset matches and 0/7 intended-hello matches.
All seven personal attempts abstained and could not start composition from an
empty turn. These runs reused cached landmarks; they are not new capture evidence.

The real doctor + tomorrow flow required an explicit appointment purpose, generated
a local LLM suggestion, and preserved the edited approval exactly. Duplicate
approval, approval after new analysis, and approval after reset were rejected.
The manual today example again produced “Hello, what day is today?” despite the
requested-day purpose; that semantic limitation remains.

This check found and fixed a UI bug: a failed draft request left the old sentence
and its provenance visible even though approval was disabled. New draft/analysis
requests, reset, purpose changes, and manual-concept edits now clear that stale
display. The approval backend already rejected the old draft.

After the fix, **19 backend tests and 16 browser assertions passed**. The browser
regression is [`test_mini_browser.js`](../../spikes/recognition/test_mini_browser.js): run it with Playwright
MCP's `browser_run_code_unsafe`, setting `filename` to this file while the existing
local Ishara tab is selected. It uses the real models, resets the shared turn,
and intentionally provokes HTTP 400 responses for unsupported concepts and blank
approval text. Those two console resource errors are expected negative checks.

The 360px viewport had a 360px document width; the browser was returned to its
desktop dimensions with a fresh, empty turn. Before/after screenshots and the
narrow view are local-only `artifacts/mini/helium-*.png`. This follow-up used Helium;
no separate Safari or WebKit run was performed.

### Recorded results

The original corpus, predictions, landmarks, and generated sentences are preserved
in ignored `artifacts/mini/evaluation.json` and `artifacts/mini/features/`.

- **Dataset:** 8/11 raw top-1 matches; eight candidates, three abstentions.
  Both location clips became Photograph (0.767 and 0.908); today became “they”
  (0.993). Doctor became correct (0.999); tomorrow was correct at 0.591.
- **User recordings:** 0/7 matched intended hello. The raw winners were Grey,
  Queen, Dream, Orange, King, Orange, Orange. All seven were outside the supported
  subset and were blocked. This is not improved recognition or proof of general
  unknown-sign rejection.
- **Synthetic negatives:** a black clip and a repeated first frame of a reference
  clip both abstained. The static image scored 0.891 for Nice. These two constructed
  checks do not replace real idle, transition, or unsupported-sign footage.
- **Sentence examples:** doctor + tomorrow with an explicit appointment-request
  purpose produced “Hello, I would like to schedule an appointment with your doctor
  tomorrow.” The same fragments without a purpose returned `needs_intent`.
- **Meaning failure:** today with the purpose “State the requested day” produced
  “Hello, what day is today?” That changes the speech act. The model also prepended
  greetings to several examples. Fluency is not semantic correctness.
- **Timing:** median model forward/transform time was about 20.1 ms. Median original
  whole-clip landmark extraction was about 4.23 s. Warm sentence generation in the
  five examples took about 0.25–0.52 s; first model load plus greeting took 2.34 s.
  Browser first-load generation took about 3.02 s. These are CPU measurements,
  not live sign-end-to-speech latency. Replays cache landmarks and disclose that.

The diagnostic rules were fixed before the first replay: full-vocabulary top-1
must be supported, score at least 0.5, top-two margin at least 0.15, adequate
shoulder visibility on 60% of frames and at least one hand on 20%. These are
uncalibrated development rules, not a demonstrated reliability threshold.

### Reproducibility and input contract

- OpenHands source revision: `b9ccf9eaf2a71301fc4601a64a6af06fdef04c9b`.
- Checkpoint member: `include/sl_gcn/epoch=112-step=12203.ckpt`.
- Checkpoint archive SHA-256:
  `0aa8eb27091dff71e5ae721a648a7410abb827c495731d3da43c55f195757a52`.
- Metadata archive SHA-256:
  `f4d229aaf56cc85266feb9d8526407513382113294dbe75fc3772f881d0fc6e3`.
- Model: 4,706,545 parameters including fixed graph tensors; 342 state entries
  loaded with strict key and shape checks. Two inert markers replace unused
  Lightning callback metadata keys while loading with `weights_only=True`.
- Qwen revision: `7ae557604adf67be50417f59c2c2f167def9a775`; safetensors file is
  988,097,824 bytes. Runtime loads local files only, with no remote Python code.
- CPU, four PyTorch threads; package versions are in `requirements.lock`.

Dependency check: the inherited environment contained both OpenCV distributions.
Its actual `cv2` runtime was 4.11.0. The conflicting `opencv-python` 5 distribution
was removed and the existing contrib 4.11 wheel reinstalled; the native binary's
SHA-256 was identical before and after, so the measured decoder did not change.
Requirements now install only `opencv-contrib-python==4.11.0.86`.

`uv pip check` also flags the legacy MediaPipe wheel's internal x86_64 platform
tag. Its native extension was inspected and contains both x86_64 and arm64 slices;
the recorded extraction ran natively on arm64. This packaging warning remains;
do not claim a fully clean dependency check or edit the wheel metadata to hide it.

`slgcn.py` imports the pinned upstream graph, FC head, network wrapper and pose
transforms unchanged, without installing its training stack. OpenHands is
Apache-2.0; its source and license are retained in the ignored clone. Qwen declares
Apache-2.0. INCLUDE video attribution and CC-BY-4.0 terms still apply.

Extraction follows `scripts/mediapipe_extract.py`: a fresh legacy MediaPipe Holistic
tracker per clip, complexity 2, 33 pose + 21 left + 21 right points, native decoded
frames, and zeros for missing landmarks. Inference discards Z/confidence, selects
the upstream 27-point preset and applies its clip-level shoulder normalization,
producing `[1, 2, frames, 27]`. There is no invented interpolation, mirroring,
automatic sign trimming, or FPS resampling in this path.

The class mapping is sorted from the original training CSV **before** numeric
prefixes are stripped, following OpenHands. It differs from our earlier INCLUDE
mapping. Current MediaPipe versions can still differ from the original training
extractor, and upstream batch padding differs from one-clip inference. This is an
executed adaptation, not a claim of exact reproduction of the published benchmark.

**Decision:** this pretrained route has not met the seated-demo expectation.
Keep the prototype as a diagnostic tool. A next step would need better representative
ISL examples and a decision about adapting the pretrained recognizer. Do not infer
that adding the language model repairs the recognition failures.

## Earlier INCLUDE transformer: setup

```sh
cd spikes/recognition
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.txt
git clone https://github.com/AI4Bharat/INCLUDE.git artifacts/INCLUDE   # for the label map
git -C artifacts/INCLUDE checkout df348f4a640060d4d39f02556d9f96851e8c46c7
.venv/bin/python fetch_clips.py        # 11 held-out dataset clips for the demo words, ~140 MB
```

The large checkpoint (`include_no_cnn_transformer_large.pth`, 205,805,173 bytes,
SHA-256 `13fc65e0a4c15baff3285b533fc90299a44546f41b548531dfe7494a636b3215`) is
downloaded to `artifacts/` on first model load.

## Commands

```sh
.venv/bin/python eval_clips.py                    # sanity check against dataset clips
.venv/bin/python live.py --list-cameras           # find the camera index (iPhone shows up here)
.venv/bin/python live.py --camera 0               # live, auto segmentation
.venv/bin/python live.py --camera 1 --speak       # speak accepted labels via macOS `say`
.venv/bin/python live.py --score hello,thankyou,hospital,location,today,tomorrow,doctor,idle,other --attempts 10
.venv/bin/python live.py --video some.mp4 --headless   # replay a recorded clip
```

The terminal app needs Camera permission (System Settings > Privacy & Security > Camera).

**The guide approximates the sampled dataset framing.** The original model uses raw
screen positions. Sampled clips show a signer at distance, head ~1/6 of
the frame height, hips in frame, **both hands at rest by the sides** for ~0.6 s, one
sign, hands back to the sides. Stand back until head, shoulders and hips sit on the
guide, copy the sign exactly as the picture-in-picture dataset clip shows it
(`--reference hello`, or automatic in scoring mode), then drop both hands.

Segmentation follows the same shape: recording starts when a wrist rises above hip
level (0.7 s of rest kept from before), ends 0.8 s after both wrists are back down.
The status line shows `rest`/`RAISED` so you can see what it thinks. Each segment is
also re-centred and scaled so its shoulders match the dataset's (`--no-normalize` to
turn that off; it preserved the small reused dataset-clip result).

Keys in the window: `q` quit, `SPACE` manual start/stop, `a` auto on/off, `g` guide,
`m` mirror, `n` next scoring target, `x` discard last attempt.

Two seated laptop sessions so far (close-up, hips out of frame) produced only
orange/warm/afternoon, and no offline fix recovered them. The stand-back test has not
been done yet. See the "Recognition" section of `PLAN.md` for the full diagnosis and
the parked test ideas. These observations do not establish a general standing-distance
requirement or rule out tracking and preprocessing differences.

## What this reproduces vs. changes from upstream

- Model, config and weights are upstream's (`include_model.py` is a 1:1 port of the
  large/small transformer so inference does not need xgboost/timm).
- **Changed:** upstream's forward applies `F.dropout(p=0.2)` even in eval mode, which
  made predictions non-deterministic; it is now training-only.
- Preprocessing follows `generate_keypoints.py`/`dataset.py`: legacy MediaPipe Hands+Pose,
  first 25 pose landmarks (the removed `upper_body_only` model's set), wrist-distance hand
  slot swap, NaN + linear interpolation, scaling to 1920x1080, 134 values per frame,
  pad/truncate to 169 frames. Live segments are resampled to the dataset's 25 fps.
- Segmentation (wrist raised -> start with pre-roll; wrists down for 0.8 s -> stop)
  is ours. The model
  only ever saw pre-cut single-sign clips and has no "unknown" class; the `--threshold`
  on top-1 probability is the only abstain mechanism.

## Evidence so far (20 Oct 2026, Mac, CPU)

Official INCLUDE *test-split* clips, 25 fps, 1920x1080, same studio/signers as training:

| clip | expected | top-1 | p |
| --- | --- | --- | --- |
| doctor/MVI_4471 | doctor | **slow** | 0.47 (doctor 0.43) |
| hello/MVI_0029, MVI_9914 | hello | hello | 0.96, 0.99 |
| hospital/MVI_3481, MVI_3639 | hospital | hospital | 0.99, 1.00 |
| location/MVI_3341, MVI_3342 | location | location | 0.98, 0.98 |
| thankyou/MVI_0111, MVI_9948 | thankyou | thankyou | 0.80, 0.97 |
| today/MVI_4616 | today | today | 0.85 |
| tomorrow/MVI_5477 | tomorrow | tomorrow | 0.90 |

10/11 top-1. Model forward ~10 ms per clip; MediaPipe landmarks ~30 ms per 1080p frame
(the live bottleneck). The auto-segmenter run over the same files (`live.py --video`)
found the sign and matched these predictions.

This is a small pipeline check, not proof of exact upstream equivalence. It says nothing yet about our
signers, our camera, idle/unknown behaviour, or continuous signing; that is what the
scoring mode is for. No Deaf participant validation.

## Vocabulary note

In the class map: hello, thankyou, time, today, tomorrow, doctor, hospital, location.
Not in it: wait, repeat, stop, yes, no, appointment.
