# Validate the pretrained AI4Bharat INCLUDE recognizer

**Status:** ready for teammate validation; recognition has not been run by Ishara.
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

- [ ] Exact source revision, checkpoint hash and working environment documented.
- [ ] Trained checkpoint loads with the expected 263-output architecture; no training.
- [ ] At least one genuine clip produces a real prediction; its source/split is clear.
- [ ] Small supported/negative clip evaluation reported with denominators and timing.
- [ ] Empty/invalid input and idle/unknown behavior described, including unsafe cases.
- [ ] Runnable minimal harness or a reproducible blocker report committed in a PR.
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

### Teammate result summary — fill after testing

- Verdict: **PENDING**
- Source revision / checkpoint SHA-256:
- Environment / machine:
- Real predictions and evaluation counts:
- Latency / memory observations:
- Unknown/idle handling:
- API smoke test, if attempted:
- Blockers and recommended next step:
