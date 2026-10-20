# Validate the pretrained AI4Bharat INCLUDE recognizer

**Current handoff:** [backend capability and next steps](../HANDOFF.md). This file
preserves the original INCLUDE task and its execution. The later SignCLIP
reference comparison and fixed-template composer are covered in the handoff and
active [PLAN.md](../../PLAN.md); do not restart this historical task as if no
recognizer had been run.

**Status:** Task A done in-house on 20 October 2026; Task B incomplete.
Following the methods study, the user authorized a miniature using the separate
OpenHands SL-GCN checkpoint. It runs, but the new replay scored 8/11 selected
dataset clips and 0/7 intended-hello recordings. Its local LLM/approval pipeline
also exposed a sentence-meaning error. See the
[miniature results and commands](../../spikes/recognition/README.md).
The original INCLUDE checkpoint results below are preserved separately. See the
[recognition landscape](<../reports/ISL recognition landscape.md>) and
[source audit](<../research_notes/ISL recognition source audit.md>).
Results are preserved below; code is in `spikes/recognition/`.
**Owner:** recognition/backend teammate. **Priority:** feasibility spike.

## What we want to find out

Can we reuse an already-trained Indian Sign Language model on the development Mac,
then expose its predictions to the iPhone through our own small API, without training
a new model? This can be investigated independently of the Bolna/call-audio gate.

In plain language: download their trained model, give it a short video of a known
sign, and check whether it returns the right label. “Inference” means running the
trained model to make a prediction. It does not mean training or recreating it.

There is **no verified official hosted INCLUDE inference API** in our research.
The proposed API would be a wrapper that we host on a Mac/server ourselves.

## Exact starting point

- Repository: [AI4Bharat/INCLUDE](https://github.com/AI4Bharat/INCLUDE).
- Source revision observed on 19 October 2026:
  `df348f4a640060d4d39f02556d9f96851e8c46c7`.
- Start from the [published evaluator at that revision](https://github.com/AI4Bharat/INCLUDE/blob/df348f4a640060d4d39f02556d9f96851e8c46c7/evaluate.py).
  It constructs the **large transformer, 263 classes** and loads
  `include_no_cnn_transformer_large.pth`.
- [Pinned weight manifest](https://github.com/AI4Bharat/INCLUDE/blob/df348f4a640060d4d39f02556d9f96851e8c46c7/pretrained_links.json).
  The non-CNN weights have real URLs; CNN entries include placeholders.

| Checkpoint | Exact download bytes | Approximate decimal MB |
| --- | ---: | ---: |
| Large transformer: `include_no_cnn_transformer_large.pth` | 205,805,173 | 205.8 |
| Small transformer: `include_no_cnn_transformer_small.pth` | 46,230,805 | 46.2 |
| LSTM: `include_no_cnn_lstm.pth` | 86,980,734 | 87.0 |

These sizes were read from successful HTTP range-response headers, without a full
download or model load. They describe checkpoint files, **not** installed dependency
size, model-only tensor size, RAM use or measured latency. Use the large checkpoint
first because it matches the existing evaluator; smaller is an optional comparison.

## Task A — reproduce one real prediction

1. Pin the source revision above and create an isolated Python environment. Record
   the working Python/package versions. Keep this separate from the iPhone app.
2. Download the exact large checkpoint. Record its SHA-256 after downloading so
   another teammate can reproduce the artifact. Do not train or download the entire
   dataset as the first step.
3. Inspect the published preprocessing and model definition before changing packages.
   Their hand/body landmark geometry, ordering, scaling, missing-point handling and
   sequence length must agree with the checkpoint.
4. Get one short, labeled sign clip with known provenance and usable terms. A clip
   used during model training is acceptable for a loading smoke test only; label it
   accordingly and do not report it as held-out recognition accuracy.
5. Run file inference. Preserve the original expected label and record predicted
   label, optional top-k scores, preprocessing time, inference time and failures.
6. Return a minimal runnable script plus pinned environment/setup instructions. If
   blocked, return the exact compatibility problem and the smallest proposed fix.

### Known code risks to investigate

- The upstream requirements are not version-pinned and the code uses older library
  APIs. A fresh install of every latest package is not established to work.
- The pose extractor uses `upper_body_only=True` and a **25-body-point convention**;
  its combined input is **134 coordinates per frame**. Verify compatibility with
  the selected landmark runtime; do not silently substitute differently ordered
  landmarks or assume a 33-point output is equivalent.
- The evaluator pads clips to a fixed length. Check long/empty/poorly framed clips
  explicitly rather than allowing negative padding or missing-landmark crashes.
- Upstream inference returns the most likely known class. That is not an unknown
  detector and must not automatically trigger speech on every camera segment.
- The evaluator selects CUDA when available and otherwise CPU. Mac GPU acceleration
  and end-to-end performance are not validated by that code path.

## Task B — check whether it is useful for our demo

After Task A works, test a small set of supported signs on separate clips/sessions,
plus idle hands, unsupported signing, repeated signs and bad framing. Start with
words that actually exist in the checkpoint rather than relabeling another sign.

Verified in the published map: **HELLO, THANK YOU, TIME, TODAY, TOMORROW, DOCTOR,
HOSPITAL, LOCATION**. Absent under those labels: **WAIT, REPEAT, STOP, YES, NO,
APPOINTMENT**. Check actual sign variants before selecting the final demo vocabulary.

For every clip record:

| Field | Required content |
| --- | --- |
| Clip ID | Non-identifying local test ID |
| Source and split | Provenance/license; smoke-test, development or held-out |
| Expected meaning | Known sign label, idle, unsupported, or invalid input |
| Prediction | Top-1 label; top-k and scores if exposed |
| Decision | Accept, abstain, or input error; record the gating rule |
| Timing | Preprocessing, model inference and total clip-to-text, separately |
| Conditions | Device/camera, session, framing and relevant failure notes |

Report counts and denominators, incorrect accepted labels and abstentions. Tune any
threshold on separate development clips and record it before evaluating held-out
clips. Model confidence is not measured correctness. Do not call a split signer-
independent unless signer identities actually support that claim.

## Task C — optional API smoke test after recognition works

Proposed flow, not an existing upstream endpoint:

`iPhone short clip → our POST /recognize → matching preprocessing → INCLUDE → text`

Run on the Mac first, reachable over the same Wi-Fi. USB app installation does not
automatically provide this network connection. Add a remote deployment only later.
Return a stable sign label or explicit unknown/error, top candidates if available,
and measured processing duration. Never return invented sentence meaning or silently
fall back to mocked predictions. Do not connect uncertain output to call speech.

No iPhone model conversion, cloud provisioning, full sentence translation or Bolna
integration is required for this validation task. Keep keys, private clips, weights,
environments and generated artifacts out of Git; share synthetic/authorized evidence.

## Deliverable and completion criteria

- [x] Exact source revision, checkpoint hash and working environment documented.
- [x] Trained checkpoint loads with the expected 263-output architecture; no training.
- [x] At least one genuine clip produces a real prediction; its source/split is clear.
- [ ] Small supported/negative clip evaluation reported with denominators and timing.
      (Dataset clips: done, 10/11. Our own signers: 2 sessions, 0 correct, see summary.
      Negative/idle set: not run.)
- [ ] Empty/invalid input and idle/unknown behavior described, including unsafe cases.
      (Partly: see "Unknown/idle handling" below. No systematic negative run yet.)
- [ ] Runnable minimal harness or a reproducible blocker report committed in a PR.
      (Harness exists in the working tree, not committed.)
- [ ] Recommendation: reuse as-is, adapt preprocessing, compare a smaller model,
  try a different pretrained route, or reject for this demo, with evidence.

Completion of the investigation does **not** mean recognition is good enough for
automatic speech. Make that go/no-go recommendation from the measured errors. We
have no Deaf participant validation; team reenactments do not establish natural ISL
translation or usability. Isolated-sign predictions do not prove seamless continuous
conversation.

## Sources and alternatives

- [Pinned class map](https://github.com/AI4Bharat/INCLUDE/blob/df348f4a640060d4d39f02556d9f96851e8c46c7/label_maps/label_map_include.json)
- [Pinned preprocessing](https://github.com/AI4Bharat/INCLUDE/blob/df348f4a640060d4d39f02556d9f96851e8c46c7/generate_keypoints.py)
- [Pinned code license (MIT)](https://github.com/AI4Bharat/INCLUDE/blob/df348f4a640060d4d39f02556d9f96851e8c46c7/LICENSE)
- [Original INCLUDE dataset (CC-BY-4.0)](https://zenodo.org/records/4010759)
- [Broader pretrained/Jev/Laya/video-model comparison](<../research_notes/Ishara hackathon product directions/recognizer-reuse-options.md>)

### Result summary (20 October 2026, done in-house)

- **Verdict: UNDECIDED.** The checkpoint runs in our adapted harness. No intended
  hello segment was recognized in two seated laptop sessions. Framing is a possible
  contributor; the root cause and suitability for the demo remain unresolved.
  The selected clips have been reused for tuning and are now development examples.
- **Source revision / checkpoint:** INCLUDE `df348f4a640060d4d39f02556d9f96851e8c46c7`;
  `include_no_cnn_transformer_large.pth`, 205,805,173 bytes, SHA-256
  `13fc65e0a4c15baff3285b533fc90299a44546f41b548531dfe7494a636b3215`. 263 output
  classes, 17.1 M parameters, loads with `strict` state-dict matching.
- **Environment / machine:** MacBook, Apple M5, 24 GB, macOS 27.0.1. Python 3.11.15
  via uv; torch 2.14.1, transformers 4.57.6, mediapipe 0.10.21, opencv 5.0.0,
  numpy 1.26.4, pandas 3.0.6 (`spikes/recognition/requirements.txt`, full freeze in
  `requirements.lock`). CPU only. Three compatibility fixes were needed:
  mediapipe must be <0.10.22 (later versions removed the legacy `mp.solutions` Hands
  and Pose that upstream preprocessing uses); transformers must be <5 (standalone
  `BertLayer` breaks in 5.x) and needs `attn_implementation="eager"`; the removed
  `upper_body_only` pose option is replaced by the first 25 of 33 landmarks (same
  ordering). One upstream bug fixed: `F.dropout(p=0.2)` ran at inference, making the
  same clip give different answers; it is now training-only.
- **Real predictions, dataset clips** (official test split, 11 clips fetched
  individually from the Zenodo zips via HTTP range requests, 139 MB; same studio and
  signers as training, so this is a pipeline check, not generalisation):
  top-1 **10/11**. hello 0.96, 0.99; thankyou 0.80, 0.97; hospital 0.99, 1.00;
  location 0.98, 0.98; today 0.85; tomorrow 0.90; doctor **wrong** (slow 0.47 vs
  doctor 0.43). With the live segmenter and body normalisation applied to the same
  files: 8/9 accepted at threshold 0.5, doctor correct at 0.97, tomorrow 0.48.
- **Real predictions, our signer** (laptop webcam, seated, 1280x720):
  session 1, waving "hi", 5 segments of 5-9 s: warm/orange/author, best orange 0.88.
  Session 2, attempted reference salute, 30 fps, 2 segments of 4-5.5 s: warm 0.59,
  orange 0.63. **0/7 hello.** Offline replays of those clips with body re-centring and
  scaling, single-salute windows, dataset rest frames spliced in, and mirroring all
  stayed on orange/afternoon/author/queen. Observed framing differences: dataset shoulders sit at
  (0.50, 0.38) of the frame, width 0.14, in every clip; ours were at (0.55, 0.85),
  width 0.28-0.36, hips out of frame, resting hand never visible, no rise/fall of
  the arm. Dataset clips always contain both hands and ~0.6 s of rest before and
  after the sign.
- **Latency / memory:** model forward ~10 ms per clip on CPU. MediaPipe hands+pose
  ~19 ms per frame in a parallel benchmark (31 ms serial). The second session
  captured about 30 fps at 720p. The segmenter has a 0.8 s end wait, but total
  sign-end-to-text latency and memory use have not been systematically measured.
- **Unknown/idle handling:** none in the model. It always returns one of 263 signs;
  a wave scored 0.88 for "orange" and a salute 0.63 for "orange". The only abstain
  mechanism is the top-1 probability threshold (0.5 in the harness), and 0.59-0.88
  on wrong answers shows that threshold alone is not safe. A negative set (idle hands,
  unsupported signs, bad framing) has not been run yet.
- **API smoke test:** not attempted; not needed to answer the accuracy question.
- **Blockers and recommended next step:** tests are paused. Use the methods and
  dataset research to choose a route before resuming. A stand-back trial remains
  an optional diagnostic, not a decisive generalization test. Any final comparison
  needs fresh examples from the intended seated setup, with appropriate ISL review.
  Vocabulary gap stands regardless: wait, repeat, stop, yes, no, appointment are not
  classes.
