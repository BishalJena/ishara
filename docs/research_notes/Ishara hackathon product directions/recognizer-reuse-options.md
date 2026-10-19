# Gesture-to-text with the least new model work

Checked 19 October 2026. This is source and artifact-access research, not a recognition
benchmark. No recognizer was executed, no full checkpoint/dataset was downloaded,
and no signing video was sent to an external inference service. The existing phone
diagnostic still has camera preview and speech controls, not sign recognition.

## Recommendation

Do not start with model training or iPhone model conversion. First compare a reused
ISL checkpoint with two training-free API candidates on the same small, labeled
clip set. Run recognition on the Mac initially and return bounded text to the phone.
This is a disclosed Mac-backed prototype, not on-device or offline recognition.

1. **Specialist baseline:** AI4Bharat INCLUDE's pretrained temporal transformer.
   Its exact evaluator checkpoint and two alternatives answered public byte-range
   requests successfully. This is the clearest verified starting point with no
   training. Preserve its expected feature extraction and class mapping.
2. **Fast challenger:** Jev image-history choice, with verified ISL reference
   examples, a small candidate inventory, and an explicit unknown/no-sign option.
   Image input exists, but ISL recognition quality is unestablished.
3. **Video challenger:** Gemini video understanding, using adequate temporal
   sampling and the same bounded output choices. Video support is established;
   reliable signing translation is not. Test rather than assume it works.

Select the smallest implementation that passes held-out clips, idle/unknown inputs
and actual phone-camera clips. Only then wire it into speech. Laya is optional
downstream decision logic; it does not replace the visual recognizer.

The quickest code path and the quickest reliable result may differ. API prototypes
require less setup; a pretrained specialist has direct ISL training but more old
dependency/preprocessing work. These effort comparisons are engineering judgments.

## Options audited

| Route | What already exists | Work still required / decision |
| --- | --- | --- |
| **AI4Bharat INCLUDE** | Pretrained isolated-sign LSTM/transformer weights, inference script, 263-class label map. | First specialist candidate. Adapt old dependencies and preserve temporal preprocessing. Needs boundaries, abstention and duplicate suppression for live input. |
| **AI4Bharat OpenHands** | INCLUDE BiLSTM, BERT, SL-GCN and ST-GCN checkpoint/config bundles, inference tooling. | Alternate specialist runtime. Repository says no longer maintained; package name must be distinguished from unrelated coding-agent software. |
| **Community complete ISL apps** | signBridge publishes inference-client code and a hosted model listing; Happy Club publishes a full recognition app. | Inspect actual weights and provenance rather than importing their whole application. Access/packaging gaps described below prevent treating either as a ready dependency. |
| **Community standalone checkpoints** | Abs6187 exposes actual checkpoint, metadata and configuration files. | Accessible, but published metadata/config specify only 8 classes despite broader model-card claims; linked code repository returned 404. Not first choice. |
| **Jev visual choices** | Experimental image input, visual criteria and image-history requests. | Minimal model-code path worth testing against a few supported signs. Frame history is not native video ingestion or a verified ISL model. |
| **Hosted general video model** | Gemini accepts video and configurable temporal sampling. | Low integration effort, new API access and recurring inference/network costs. Must test hand movement, unknown inputs and meaning preservation. |
| **Local general vision model** | Qwen3-VL publishes video-capable weights. | Avoids a hosted API, but adds model download/runtime/memory work. No verified ISL performance found. Secondary to the API experiment. |
| **One/few-shot reference matching** | CISLR research demonstrates cross-language feature transfer and prototype recognition. A small landmark-sequence matcher is another engineering option. | Can avoid training a new network, but still needs genuine reference clips, normalization and held-out testing. No claim that a few examples generalize to new signers. |
| **Text decision model** | Laya/MLX runs typed text/structured-state choices locally on a Mac. | Could rerank observed candidates or manage state. No image encoder/sign recognizer established. Extra dependency unless it demonstrably improves results. |
| **Continuous translation research** | iSign/ISLTranslate/PoseStich-SLT provide sentence-level data and research baselines. | Bigger scope, asset/access/licensing/setup work; not established as a drop-in real-time phone translator. Keep for later if bounded recognition cannot cover a useful task. |
| **Commercial sign APIs / Google product features** | Sign-Speak documents ASL APIs; Google SL2T ships ASL-to-English on Pixel. | Wrong demonstrated language/platform for this ISL iPhone target. No usable public ISL integration established by these sources. |
| **Canned gestures / alphabet models** | MediaPipe common gestures; public ISL alphabet/digit classifiers. | Easy to install, but do not satisfy conversational ISL. Useful only for explicitly labeled diagnostic controls or a disclosed spelling mode. |
| **Small fine-tune** | Existing landmark/video encoders can be reused. | Last resort if required signs are absent or no-training candidates fail. Fine-tune a small head/adapter rather than pretraining from scratch; still needs representative labeled data. |

## Concrete artifact findings

### INCLUDE and OpenHands

- [Original INCLUDE code](https://github.com/AI4Bharat/INCLUDE) has an
  [evaluation script](https://github.com/AI4Bharat/INCLUDE/blob/master/evaluate.py)
  that loads a large transformer with 263 outputs. It expects its own landmark
  geometry and fixed-length sequence handling. File inference is not continuous
  segmentation or translation.
- The [weight manifest](https://github.com/AI4Bharat/INCLUDE/blob/master/pretrained_links.json)
  contains literal placeholder links for CNN variants, but working URLs for
  non-CNN models. Probed the large/small INCLUDE transformer and LSTM URLs:
  **206**, receiving 1,024 bytes each. This confirms artifact access, not successful
  loading, accuracy or runtime compatibility.
- Checked the [actual label map](https://github.com/AI4Bharat/INCLUDE/blob/master/label_maps/label_map_include.json):
  HELLO, THANK YOU, TIME, TODAY, TOMORROW, DOCTOR, HOSPITAL and LOCATION are present.
  WAIT, REPEAT, STOP, YES, NO and APPOINTMENT are absent under those labels. Do not
  pretend filtering a label map adds missing signs.
- The code is MIT. The [original dataset record](https://zenodo.org/records/4010759)
  reports CC-BY-4.0, confirmed through its API. Retain source attribution and verify
  any separate assets/checkpoint terms when redistributing.
- [OpenHands model bundles](https://openhands.ai4bharat.org/en/latest/instructions/models.html)
  include pretrained configuration and parameters; the
  [source checkpoint index](https://github.com/AI4Bharat/OpenHands/blob/main/docs/_static/checkpoints.csv)
  names public GitHub release bundles. Its docs page returned 403 to a direct fetch,
  while the source index and cached official documentation were accessible. The
  [repository](https://github.com/AI4Bharat/OpenHands) says it is no longer maintained.

### Community alternatives: useful leads, not verified replacements

- [Abs6187/isl-models](https://huggingface.co/Abs6187/isl-models) has accessible
  checkpoint files: a 1,024-byte range probe returned 206. Its
  [metadata](https://huggingface.co/Abs6187/isl-models/blob/main/metadata.json) and
  config list **8** classes: Hospital, How Are You, Monday, Night, Shoe, Street,
  Thank You, Yellow. This conflicts with the card's much broader counts. The linked
  inference repository was unavailable. MIT is declared on the model card; that
  alone does not resolve the missing implementation or evaluation mismatch.
- [signBridge](https://github.com/Uni-Creator/signBridge) is MIT code and reports
  76 word classes, with author-reported 66.84% top-1 on 187 test samples. Its
  [weight repository](https://huggingface.co/Creator-090/isl-swin3d-model) exposes a
  filename but requires gated access/contact sharing: a direct file probe returned
  **401**. Its public Space was listed sleeping; a health request timed out. No
  terms were accepted and no signing video was uploaded. Code inspected on current
  main is an inference-service client, not proof the trained service is locally
  self-contained. Model/data terms need separate review from its MIT code license.
- [Happy Club](https://github.com/sandeepsahu1808/Happy-Club-AI-Sign-Language-Translation)
  documents a 79-class pipeline, but the inspected repository tree did not provide
  a corresponding trained `.pt`/`.pth`/ONNX checkpoint. Architecture and screenshots
  are not a downloadable trained recognizer.
- [Hemg's classifier](https://huggingface.co/Hemg/Indian-sign-language-classification)
  has safetensors and Apache-2.0 card metadata, but its config maps only letters
  and digits. KairoAI publishes a TFLite model, but its evaluation report likewise
  lists A–Z and 1–9. Large reported accuracy numbers there do not establish word
  recognition or signer-independent conversation performance.

### Jev, Laya and general visual models

- [Jev's live image documentation](https://docs.typesafe.ai/images) explicitly
  supports images in state/instructions/criteria, including visual examples and
  ordered image histories, behind `TypeSafe-Danger-Zone-Images: true`. Jev 1.13 and
  1.14 support images according to this page. Context7 returned older text-only
  material, so the newer live image guide controls this capability finding.
  Pin a concrete model version for any comparison. A returned confidence is not
  a measured ISL correctness guarantee.
- Proposed Jev test: compare a short ordered frame history to verified reference
  histories for supported signs, returning a label or UNKNOWN. This is our
  experiment design, not a vendor-proven ISL capability. API access is required;
  no Jev inference was run.
- [Laya MLX](https://github.com/mizorewww/laya-mlx) documents text/structured-state
  decisions on Apple Silicon macOS, Python 3.11+, with local downloaded weights.
  Its fast decision benchmarks do not include a visual sign-recognition stage.
  It cannot recover a true sign missing from the candidates merely by reranking.
- [Gemini video documentation](https://ai.google.dev/gemini-api/docs/generate-content/video-understanding)
  establishes video input and configurable FPS. Default sparse sampling can omit
  movement, so test adequate temporal sampling. No ISL quality guarantee follows
  from general video understanding.
- [Qwen3-VL's model card](https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct)
  establishes downloadable video-capable model weights, not an ISL-specialized
  checkpoint. It is a local general-vision comparator if API access is undesirable.
- A [2026 specialist study](https://openaccess.thecvf.com/content/CVPR2026W/MSLR/papers/Varanasi_Isolated_Sign_Language_Recognition_via_MediaPipe_Landmarks_A_Case_Study_CVPRW_2026_paper.pdf)
  reports temporal landmark recognition and limitations of tested VLM approaches.
  That motivates a measured comparison; it does not determine Jev's performance.

### Other routes and exclusions

- [CISLR](https://github.com/Exploration-Lab/CISLR) includes a prototype-based
  one-shot recognition approach and extracted features, with CC-BY-NC-4.0 dataset
  terms. This is a real no-new-network-training research route, but no ready
  phone inference bundle was verified in this audit.
- [iSign](https://huggingface.co/datasets/Exploration-Lab/iSign) has phrase/sentence
  data and research/non-commercial terms; a dataset is not a ready recognizer.
- [Sign-Speak](https://app.theneo.io/sign-speak/sign-speak-api/api-specifications/asl-recognition)
  documents ASL recognition and streaming services. That does not establish ISL.
- [Google SL2T](https://deepmind.google/blog/putting-sign-language-ai-into-users-hands/)
  starts with ASL-to-English in Pixel 11 products. No public ISL/iPhone API or usable
  SignGemma ISL checkpoint was established in this search.
- [MediaPipe's stock recognizer](https://developers.google.com/edge/mediapipe/solutions/vision/gesture_recognizer/index)
  covers seven common hand gestures. Hand/pose landmark detectors supply geometry;
  neither is a conversational ISL translator.

## Minimum comparison before integrating speech

Use the same small supported inventory for every candidate. Obtain separate
reference/development/test clips with usable terms; keep recording sessions and
signers separated where metadata allows. Include wrong signs, idle hands, signing
transitions, left/right mirroring and repeat gestures. We have no Deaf participant
validation; team reenactments can test mechanics, not natural ISL or usability.

Measure correct labels, wrong accepted labels, abstentions, repeated outputs and
sign-end-to-text latency. Choose thresholds on development clips before evaluating
the test clips. A high softmax/decision confidence alone is not acceptance evidence.
For a tiny demo, preserve exact supported meaning with templates; do not ask a
language model to invent appointments, dates or intentions from sparse labels.

Automatic segmentation and natural continuous signing remain separate work even
if a pretrained model labels isolated clips correctly. Initially showing text for
inspection avoids turning every recognition mistake into speech on a real call.
