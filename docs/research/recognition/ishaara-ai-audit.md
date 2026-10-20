# Ishaara AI: website, paper and repository audit

Checked 20 October 2026. This concerns the independent project at
[ishaara.app](https://www.ishaara.app/models), not this repository.

## Decision

**Useful bounded recognition work, with real released artifacts; insufficient
evidence of general ISL translation or reliability for our appointment scenario.**
The public GitHub is valuable for studying a small temporal recognizer and its
data collection. It is not a reproducible release of the current website.

The main finding is that three different systems must be distinguished:

- The published paper and released GRU: five greeting/courtesy phrases plus blank.
- The old repository's object detector: a Roboflow browser integration, with an
  eleven-label confusion-matrix image.
- The current website: an eighteen-label YOLOv8-style image detector, prediction
  aggregation, server-side sentence requests, and browser speech synthesis.

Do not interpret the GRU paper's accuracy, the detector's mAP, and the website's
sentence output as evidence for one end-to-end system.

## Scope and reproducibility

Reviewed public source, notebook cells and saved outputs, checkpoint configuration
JSON, label-pickle strings using static opcode inspection, published metric images,
the linked paper, deployed JavaScript and the current model JSON endpoints.
No imported project code or serialized Python objects were executed. No signing
recognition benchmark, live camera session, training or paid inference was run.

Repository: [vnrr2023/Ishaara_Ai](https://github.com/vnrr2023/Ishaara_Ai).
Reviewed commit: `98e7a709e72e9fb81c4fc4812d2abbf9c9f546a8`, dated 28 February 2025.
The old `ishaara_ml` link redirects to this repository. The remote advertised
one branch, `main`, and no tags. GitHub reports no license; the tree has no
license, dependency manifest or automated test suite. Public visibility does
not establish permission to redistribute its code, weights or dataset.

The website has later assets, so deficiencies in an old notebook should not be
automatically attributed to its current deployed model.

## 1. The paper and released GRU

Primary paper: [Word-Based Indian Sign Language Translator Using Seq2Seq Model](https://doi.org/10.7759/s44389-025-03530-7),
published 5 September 2025.
[Publisher PDF](https://assets.cureusjournals.com/artifacts/upload/original_article/pdf/3530/20250905-94170-gv595i.pdf).

### What it actually recognizes

The released label file contains:
`blank`, `hello`, `how are you`, `sorry`, `thank you`, `welcome`.

Its flow is:

**30 camera frames → MediaPipe Holistic → 1,662 values per frame →
GRU(64) → GRU(128) → GRU(32) → Dense(64) → Dense(32) →
six-way softmax.**

The 1,662 values are 33 pose landmarks × 4 values, 468 face landmarks × 3,
and 42 hand landmarks × 3. Missing streams are zero-filled. The inference
script does not perform shoulder centering or scaling.

Although called “Seq2Seq”, the released network is a sequence-to-one classifier:
one video window produces one class. There is no sentence decoder, gloss
alignment or variable-length text generation in this recognizer. “How are you”
is one learned class, not three independently translated words.

Sources: [inference script](https://github.com/vnrr2023/Ishaara_Ai/blob/98e7a709e72e9fb81c4fc4812d2abbf9c9f546a8/GRU%2BMediapipe/Version_2/main.py),
[checkpoint directory](https://github.com/vnrr2023/Ishaara_Ai/tree/98e7a709e72e9fb81c4fc4812d2abbf9c9f546a8/GRU%2BMediapipe/Version_2/models),
[label file](https://github.com/vnrr2023/Ishaara_Ai/blob/98e7a709e72e9fb81c4fc4812d2abbf9c9f546a8/GRU%2BMediapipe/Version_2/v2_classes.pickle).

### Data and evaluation

The paper reports collecting **900 sequences, 150 per class**, from students at
a Deaf education institution with teacher guidance. This involvement is a useful
data-collection precedent, but is not evidence of usability in an unscripted
appointment conversation.

The paper's comparison table gives **99.8% training accuracy and 98.98% testing
accuracy**, with 24 epochs. Some surrounding prose emphasizes 99.8% without this
distinction. Do not report 99.8% as its independent test result.

The released V2 classification-report image shows **45/45 correct**, with only
6–11 test samples per class. This image does not document a signer-held-out or
session-held-out split, nor establish its correspondence to the paper's test.
The six-class training dataset, split manifest and exact V2 training run are
not available in the reviewed tree.

There is a specific evaluation defect in the earlier four-class
[training notebook](https://github.com/vnrr2023/Ishaara_Ai/blob/98e7a709e72e9fb81c4fc4812d2abbf9c9f546a8/GRU%2BMediapipe/model_tester_v1.ipynb):
after fitting a GRU with a 90/10 random split, later cells create new 80%, 50%
and 90% test splits from the same complete dataset and evaluate the already
trained model. Those new test sets can contain training examples. The notebook
also uses the original test set for epoch-by-epoch validation. These later
scores are not clean held-out estimates.

**Limit of this finding:** this is directly visible in the V1 notebook. It
does not prove the same exact procedure generated the V2 image or paper result.
Neither the paper nor the inspected release establishes performance on unseen
signers, independent sessions, out-of-vocabulary signs or our camera setup.

### Framing and recognition controls

The [readiness script](https://github.com/vnrr2023/Ishaara_Ai/blob/98e7a709e72e9fb81c4fc4812d2abbf9c9f546a8/GRU%2BMediapipe/Version_2/ready.py)
estimates distance from eye separation using a fixed assumed eye distance and
focal length. It admits an estimated **176–192 cm** range before checking
readiness. This is a camera-dependent heuristic, not measured depth sensing.
It does not establish compatibility with our seated propped-phone setup.

The recognizer predicts on successive non-overlapping 30-frame blocks, accepts
the maximum score above 0.7, and suppresses consecutive duplicate labels.
There is no explicit sign-boundary detector or calibrated unknown-sign rejection.
The blank class is useful, but it is not a substitute for unsupported-sign tests.

## 2. What the current website actually deploys

The [live translator](https://www.ishaara.app/translate) serves JavaScript that
loads separate desktop/mobile TensorFlow.js graph models, cached in IndexedDB
under names containing `yolov8`.

The public model descriptions are:

- [Desktop model JSON](https://www.ishaara.app/api/model/desktop/model.json?v=v1.0.0):
  input `[1,640,640,3]`, 25 weight shards.
- [Mobile model JSON](https://www.ishaara.app/api/model/mobile/model.json?v=v1.0.0):
  input `[1,640,640,3]`, 3 weight shards.

The manifests imply about **98.77 MiB desktop / 10.03 MiB mobile weight storage**.
These are calculations from stored shapes and dtypes, not measured download
traffic, runtime memory, latency or trainable-parameter counts.

The deployed class list is:
`I`, `afternoon`, `bye`, `deaf`, `good`, `hello`, `home`, `how are you`,
`i am fine`, `indian`, `live`, `morning`, `namaste`, `name`, `sorry`,
`thank you`, `time`, `yes`.

**None of doctor, hospital, appointment, today or tomorrow is in this list.**

### Recognition and sentence path

The inspected code performs:

1. Read one RGB camera frame, pad to square, resize and divide by 255.
2. Run the image detector and decode boxes/class scores.
3. Apply non-maximum suppression with IoU 0.45 and score threshold 0.2.
4. Pass the highest-scoring surviving label to an aggregator.
5. Accept a label once it accumulates five votes in a buffer of up to twenty
   valid detections, then reset that buffer; suppress adjacent duplicate labels.
6. After every three accepted labels, POST those words to `/api/translate`.
7. Check word overlap in the returned sentence and speak it using browser speech
   synthesis when voice output is enabled, which is the initial setting.

This is **image-based recognition with repeated-detection filtering**. The model
does not receive a temporal clip. Repeated agreement can reduce visual flicker;
it cannot teach an image detector distinctions that require movement order.
Whether these eighteen signs are accurately discriminated in everyday use still
requires evaluation.

The visual inference path operates locally in this code. Recognized words leave
the browser for sentence generation. The complete flow therefore is not wholly
on-device. No webcam-frame upload was identified in the inspected recognition
path; this is a source observation, not a full network/privacy audit.

The deployed sentence server's implementation/provider is not published in the
reviewed GitHub. Its older `gemini_server.py` uses Gemini Pro, which must not be
assumed to be the provider behind the current OpenAI-shaped response.

### Sentence preservation is not established

The client checks whether each input phrase contributes at least one non-stopword
to the output. It does not check negation, intent, additional facts or word order.
A local synthetic reproduction of that rule accepts:

`i + live + home` → **“I do not live at home.”**

This is a counterexample to the guard's guarantee, not an observed output from
their language model. It required no call to their sentence service.
The inspected flow automatically speaks the accepted sentence; it does not
require approval of its exact wording. Our preview/edit/approval requirement
must remain.

## 3. Other named architectures and metrics

**ConvLSTM:** real Keras/H5 checkpoints are present. The serialized model has four
ConvLSTM layers with 4/8/16/32 filters, pooling/dropout and a seven-class output.
The live script draws MediaPipe body/hand skeletons on a white image, converts
that image to grayscale, and classifies 30 such frames at 192×192. This route
does not add raw hand appearance to pose; it rasterizes pose into images.

Its labels are blank, hello, how are you, I, morning, sorry and thank you.
The provided training script loads a builder's already-completed seven-class
Conv3D/GRU network and then appends ConvLSTM layers requiring video-shaped input.
That wiring is inconsistent with the released ConvLSTM architecture. It also
derives train/test subsets from a shuffled dataset without freezing membership.
The checked-in scripts are not a clean recipe for reproducing the weights.

Sources: [ConvLSTM files](https://github.com/vnrr2023/Ishaara_Ai/tree/98e7a709e72e9fb81c4fc4812d2abbf9c9f546a8/ConvLSTM).

**Conv3D:** the README explicitly says the model was not developed to completion
because of resource constraints. The architecture stub exists; a validated
3-GB trained recognizer does not appear in the reviewed release. The website's
3-GB/32-GB-RAM statements describe their proposed implementation, not an inherent
requirement of all video recognition.

**Alphanet and Ishaara Net:** the model catalog labels these “releasing soon”.
Their metrics pages use hard-coded headline values; the shared rendering code
passes the same chart arrays for all three model IDs. This does not establish
three separately evaluated trained releases.

**Lexnet:** the metrics page gives precision 99.8%, recall 98.7%, mAP50 99% and
mAP50–95 88.9%. These are object-detection metrics, not sentence accuracy.
A [team announcement](https://www.linkedin.com/posts/rehan42_ishaaraai-accessibility-signlanguage-activity-7373573854138556416-qmpM)
describes YOLOv8 training on 41,000+ manually annotated/augmented images.
The linked paper studies the six-class GRU, not that larger image detector.
The image count does not reveal independent signers, source videos, or
augmentation-independent train/test splits.

The old repository's detector confusion matrix covers eleven labels. Its
validation montage shows one visible signer/background across the sixteen
displayed examples, including similar poses. This warrants asking about source
separation; the montage alone does not prove train/test leakage or that all data
came from one signer.

## What we should take from it

1. **Collect the target vocabulary deliberately.** Their narrow class inventory
   and teacher-supported data collection are more relevant than the headline
   model name. A complete phrase can be one class when that is the chosen task.
2. **Use a compact temporal classifier as a baseline when target data exists.**
   Their GRU is a concrete example of a small model trained on a bounded
   vocabulary. It is not evidence that three examples suffice: the paper reports
   150 sequences per class.
3. **Separate model execution from product behavior.** Local browser inference,
   mobile/desktop variants, model caching and aggregation are useful engineering
   patterns. Recognition, sentence preservation and approval require separate
   validation.
4. **Keep temporal information for dynamic signs.** The live YOLO route may work
   for visually distinctive configurations. It is not grounds to discard motion
   from our doctor/tomorrow recognition task.
5. **Use proper evaluation from the start.** Split by signer/session/source video
   before augmentation. Calibrate rejection on unsupported signs, transitions,
   incomplete signs and idle footage.

The released GRU could be a narrow comparison on shared greeting classes after
input compatibility and reuse terms are resolved. It cannot directly supply our
appointment vocabulary. The ConvLSTM/Conv3D paths add little to our immediate
experiment, and the current YOLO release lacks a complete public training/data
contract.

**Recommended action:** retain the planned pretrained-encoder/reference comparison,
and treat a small target-trained temporal classifier as a possible control when
we have fresh labeled sessions. Do not replace the backend based on this project's
published percentages. Meaningful Bolna integration and the existing-call audio
path remain separate unresolved requirements.

## Artifact fingerprints

Deployed inference bundle:
`https://www.ishaara.app/_next/static/immutable/chunks/0nzr8xmodh49s.js`
SHA-256 `0fe3ca33707b3d2c188043fc04827f9a1c5c2b630b7bbbc45be3ee5cfd740f03`.

Deployed metrics bundle:
`https://www.ishaara.app/_next/static/immutable/chunks/1-61ux2vwwxhk.js`
SHA-256 `668bab73f5a8d206664126e185eb3ab4a345d9f57e82ba9fc1e25d3f10bcbaad`.

Desktop/mobile model JSON SHA-256:
`e4836af9a32a67fc5dec0988cc44c4504708ee323c7dd34879c4ad81f5c31a80`,
`c81add4094547165c0760803c6a63f9749c3fb5da375f5716554f9648b3a0588`.

GRU V2 `.keras` SHA-256:
`d4adde92d4f21cbe1d756452d53ea9561984e6a7d154e0e547c6046a74494c91`.
ConvLSTM `.keras` SHA-256:
`bc2d5e10c1b361c7fe47f382631490532859bfdef2e8066048a471bce80adb3f`.
