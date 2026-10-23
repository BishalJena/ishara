# Recognition runbook

Local diagnostics, not a deployed recognition service.
[Handoff](../../docs/HANDOFF.md) · [Measured results](../../docs/experiments/recognition.md) ·
[Active gates](../../PLAN.md) · [Historical notebook](../../docs/archive/2026-10-20-recognition-notes.md)

Commands below run from `spikes/recognition` on the tested Mac/Python 3.11 setup.
Git and `uv` are prerequisites. Weights, videos, caches and generated evidence
stay under ignored `artifacts/`; no credentials are needed for the public models.

## Set up the browser miniature

```sh
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python setup_mini.py
.venv/bin/python fetch_clips.py
.venv/bin/python -m unittest -v test_mini test_retrieval
.venv/bin/python mini.py evaluate
.venv/bin/python mini.py serve
```

Open **http://127.0.0.1:8088**. Analyze public doctor and tomorrow clips, select
appointment-request purpose, compose, edit and approve. Approval records text
locally; speech is not connected. Supplied-concept mode is explicitly separate
from recognition.

Setup fetches OpenHands source/checkpoint/metadata and the optional Qwen assets
(about 1 GB). Default composition uses fixed templates; `--composer llm` selects
the historical LLM experiment. Evaluation writes `artifacts/mini/evaluation-templates.json`;
LLM evaluation uses `evaluation.json`.

Personal webcam clips are not distributed. Inspect download warnings and inventory:
missing public/private clips change replay denominators. The backend is a
single-user, single-turn diagnostic bound to loopback; reset between utterances.
It currently uses SL-GCN, while uncalibrated SignCLIP ranks stay in the separate tool.

For a preview proxy, allow its exact current origin:

```sh
.venv/bin/python mini.py serve --preview-origin http://127.0.0.1:64343
```

Replace that example port with the preview's actual port. Unrelated origins stay
blocked. The browser regression is `test_mini_browser.js`, runnable through
Playwright MCP's `browser_run_code_unsafe` filename argument with the local tab
selected. It exercises real public clips, resets the turn and expects two
deliberate HTTP 400 responses.

## Set up SignCLIP separately

Do not install its requirements into `.venv`: Transformers versions differ.

```sh
mkdir -p artifacts/signclip
uv venv --python 3.11 artifacts/signclip/.venv
uv pip install --python artifacts/signclip/.venv/bin/python -r requirements-signclip.txt
artifacts/signclip/.venv/bin/python setup_signclip.py
artifacts/signclip/.venv/bin/python retrieval.py replay --encoder signclip
.venv/bin/python retrieval.py replay --encoder slgcn
```

Setup fetches the pinned upstream source, ~2.4 GB multilingual checkpoint and BERT
tokenizer/config metadata; it does not fetch BERT base weights. Inference is local.
Replay compares the same saved corpus and always abstains until a fresh pilot
supports calibration. Similarities are not confidence probabilities.

SignCLIP extracts body, hands and face contours with pose-format 0.9.0 / Holistic
0.10.21 complexity 1 and upstream normalization, producing 609 values per frame.
SL-GCN has its own 27-joint input and preprocessing. Preserve raw video; their
landmark caches are not interchangeable. SignCLIP rejects more than 256 frames
rather than silently truncating. Neither path invents a missing sign.

## Capture and review

Begin with the enrollment budget in [PLAN.md](../../PLAN.md). Keep one pseudonym
and one session ID throughout a recording session, including across commands:

```sh
.venv/bin/python pilot_capture.py capture \
  --signer demo --session enrollment-01 --split enrollment \
  --concept hello --takes 3 --camera 0
```

Repeat for each of the 12 demo signs (`--concept` accepts exactly these):
hello, thankyou, yes, no, sorry, doctor, today, tomorrow, morning, afternoon,
evening, time. **SPACE** starts/stops a take;
**X** discards; **Q/escape** exits and discards an unfinished take. Keep face,
shoulders and hands visible, with a complete sign and brief neutral boundaries.
Long takes are rejected, not cropped. The camera requests 1280×720 at 30 FPS;
actual dimensions, timestamps and frame gaps are retained, with encoding at the
measured mean FPS. Camera permission may be required for the terminal app.

Every take is unverified. Raw clips and the manifest stay under `artifacts/pilot/`.
Use the printed clip ID to review tracking and check the sign against appropriate
ISL expertise/reference material:

```sh
.venv/bin/python pilot_capture.py review --id CLIP_ID
.venv/bin/python pilot_capture.py verify --id CLIP_ID \
  --note "Describe the actual sign-form review and the ISL reference used"
```

`review --headless` writes the full overlay without opening a window. Reviews
never show predictions. `verify` records your explicit label assertion and note;
tracking quality does not automatically verify ISL meaning.

For later negative collection use `--concept idle`, `transition`, `incomplete` or
`unsupported`, with an explanatory `--note` and the correct calibration/test split.
Enrollment accepts supported concepts only.

## Calibrate and evaluate

```sh
.venv/bin/python retrieval.py status
artifacts/signclip/.venv/bin/python retrieval.py calibrate --encoder signclip
.venv/bin/python retrieval.py calibrate --encoder slgcn
# Select the encoder on development evidence before inspecting the final test.
artifacts/signclip/.venv/bin/python retrieval.py evaluate --encoder signclip --fresh
```

The [active plan](../../PLAN.md) owns coverage and pass criteria. Manifests reject
duplicate videos and session/source/hash overlap across splits. Frozen policies
are bound to encoder and development fingerprints. Missing data, unverified labels,
nonfinite evidence and reject-all calibration cannot pass.

`calibrate` uses the calibration session only. It needs attempts for all 12 signs
and at least 20 negatives, then picks the cut-off (similarity plus margin over the
runner-up) that keeps the most correct accepts with **at least 60% per sign, 0 wrong
accepts and 0 negative accepts** (PLAN R2b). If no cut-off qualifies it fails rather
than freezing one that rejects everything. Besides `artifacts/retrieval/policy-<encoder>.json`
it writes and prints `artifacts/evidence/calibration-<encoder>.md`: cut-off, margin,
accepted/attempts per sign, wrong accepts and negative accepts with denominators.

## Export the iPhone bundle

```sh
artifacts/signclip/.venv/bin/python retrieval.py export-bundle --encoder signclip
```

Writes `artifacts/evidence/recognition-bundle-<encoder>.json` for the on-device
matcher (P2):

```json
{"version": 1, "encoder": "<encoder contract as canonical JSON>", "embedding_dim": 768,
 "thresholds": {"similarity": 0.0, "margin": 0.0},
 "quality": {"min_pose_fraction": 0.6, "min_hand_fraction": 0.2},
 "references": [{"id": "<clip id>", "label": "hello", "embedding": [0.0]}]}
```

It refuses when the enrollment/calibration data changed since `calibrate`, or the
loaded encoder contract differs from the frozen policy; re-run `calibrate` first.
The quality values come from `recognition_data.QUALITY`, the same constant the Mac
decision uses. References are Mac-extracted embeddings of the enrollment clips;
the parity task (P3) re-embeds them with the iOS extractor before the iPhone relies
on them. The bundle contains personal enrollment embeddings, so it stays under
ignored `artifacts/`.

`--fresh` disables feature caching. Reported batch timing still excludes capture,
ranking and display; `live_latency_validated` and `demo_ready` stay false.
If final-test findings drive changes, collect a new final test session.

## Historical INCLUDE harness

Retained for comparison; it is not the active fresh-data candidate.

```sh
git clone https://github.com/AI4Bharat/INCLUDE.git artifacts/INCLUDE
git -C artifacts/INCLUDE checkout df348f4a640060d4d39f02556d9f96851e8c46c7
.venv/bin/python eval_clips.py
.venv/bin/python live.py --list-cameras
.venv/bin/python live.py --camera 0 --reference hello
```

Reuse an existing pinned clone rather than cloning over it. First model load
downloads the checkpoint. `live.py --help` documents replay/scoring controls.
The segmentation/framing guide approximates sampled dataset conditions; it does
not establish a standing-distance requirement or reliable seated recognition.
The adapted code retains the [upstream MIT notice](INCLUDE-LICENSE.txt).

## Reproducibility notes

Requirements pin the compatible MediaPipe/OpenCV/Transformers versions; observed
freezes are local snapshots. The legacy MediaPipe wheel has a platform-tag warning,
although the inspected native extension contains arm64 and x86_64 slices and the
recorded extraction ran on arm64. Do not claim a clean cross-platform install.

Hashes and executed compatibility checks are in the
[experiment record](../../docs/experiments/recognition.md); source revisions and
input contracts are also explicit in each adapter. OpenHands is Apache-2.0 and
its license stays in the downloaded clone. INCLUDE videos have CC-BY-4.0 terms.
Consult the [source audit](../../docs/research/recognition/source-audit.md) for
separate code, checkpoint and dataset licensing considerations.
