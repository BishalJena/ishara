# ASL transfer for Ishara

Checked 20 October 2026. This is a focused source review following the miniature
experiment. No additional model was downloaded, executed, or trained.

**Later execution:** the reference comparison has now run locally. See the
[teammate handoff](../HANDOFF.md) for measured results and the fresh-data gate.
The statements below describe this source-review checkpoint.

## Recommendation

Use a pretrained sign representation and labeled ISL reference examples as the
next experiment. Compare **SignCLIP multilingual reference matching** against
the existing SL-GCN representation on the same new, session-separated recordings.
Do this before committing to training a five-class SL-GCN head.

This revises the earlier implementation order, not the requirement for trustworthy
ISL examples, abstention, explicit intent, and exact approval. Neither encoder has
demonstrated recognition on the intended setup. Five signs are a manageable first
evaluation vocabulary, not an intrinsic limit of reference matching.

## What transfers between sign languages

An encoder can learn useful hand shape, orientation, body-relative location,
movement and timing from another sign language. Its ASL output labels cannot
simply be renamed as ISL labels. ISL references or target-language adaptation
establish the association between the visual representation and the intended ISL
meaning. Shared English glosses do not establish equivalent signs.

The first task is **isolated-sign recognition**: observe a complete sign and return
a supported concept or abstention. Recognizing selected signs within uninterrupted
signing is the further task of sign spotting. Neither is full sentence translation.
We are limiting the meanings we recognize, not assuming that an incomplete hand
movement is sufficient evidence of a whole sign.

## Primary evidence

### CISLR directly studies ASL to ISL transfer

The [EMNLP 2022 paper](https://aclanthology.org/2022.emnlp-main.707/)
([full text](https://aclanthology.org/2022.emnlp-main.707.pdf), sections 4–5)
trains I3D on WLASL2000, takes its penultimate-layer features, embeds one ISL
prototype per label, and assigns a query the label of its nearest prototype.
This is directly relevant to the user's proposed low-data approach.

The authors report **16.81% top-1** on CISLR v1.0-a, with 4,765 prototype labels
and 2,285 test queries. The 43.41% result on v1.0-ab includes halves of repeated
signs from the same original recordings; the authors explicitly attribute the
increase to repeated signs by the same signer in the same setting. Neither result
is an estimate of five-sign webcam accuracy.

The [official repository](https://github.com/Exploration-Lab/CISLR) documents
videos, prototype/test CSVs and pre-extracted I3D features. That listing alone does
not establish a complete fresh-video inference release. Its dataset terms state
CC-BY-NC-4.0, irrespective of the repository's MIT code badge.

### SignCLIP offers a released multilingual encoder

The [EMNLP 2024 paper](https://aclanthology.org/2024.emnlp-main.518/)
([full text](https://arxiv.org/html/2407.01264v2)) pretrains on about 500,000
dictionary clips across up to 44 sign languages. It explicitly identifies
few-shot prompting or fine-tuning as important for out-of-domain recognition.
Its downstream ASL results are not an ISL webcam benchmark.

The [published inventory](https://github.com/J22Melody/fairseq/blob/main/examples/MMPT/data_stat_sp_lan_dis.csv)
contains `ins,6086`: 6,086 Indian Sign Language entries. That is training-inventory
coverage, not a claim of 6,086 reliably recognized live signs.

The [official instructions](https://github.com/J22Melody/fairseq/tree/main/examples/MMPT#demo-and-model-weights)
identify `baseline_temporal` as the multilingual model. The linked
[public model folder](https://drive.google.com/drive/folders/10q7FxPlicrfwZn7_FgtNqKFDiAJi6CTc)
was readable and listed `baseline_temporal_checkpoint_best.pt` at **2.43 GB**.
This is the listed checkpoint file size, not measured memory or inference cost.
Weights were not downloaded or loaded in this review.

The [current inference example](https://github.com/J22Melody/fairseq/blob/main/examples/MMPT/demo_sign.py)
uses body, full hand and face-contour pose features, shoulder normalization and
leg masking, with a 609-value frame representation. It is not compatible with
feeding our existing 27-joint SL-GCN input directly. The saved RGB recordings
can be reprocessed; our face-free cached features are insufficient for this input
contract. The README supplies a Python 3.12 inference environment, but Mac
compatibility, latency and checkpoint/data licensing still need verification
before implementation or distribution.

**Engineering preference:** start with the multilingual release, rather than
assuming an ASL-fine-tuned release will preserve more useful ISL features.
This preference is a hypothesis to test.

### HTMA supports the transfer principle, with release limitations

The [CVPR Workshops 2026 paper](https://openaccess.thecvf.com/content/CVPR2026W/MSLR/papers/Varanasi_Isolated_Sign_Language_Recognition_via_MediaPipe_Landmarks_A_Case_Study_CVPRW_2026_paper.pdf)
pretrains on WLASL2000, MS-ASL and ASL-Citizen before ISL fine-tuning.
It reports 95.88% top-1 on the original INCLUDE split, 83.82% on a stricter split,
and 19.20% on CISLR. The stricter split approximates signer groups from recording
IDs. These are author-reported results under their protocols, not directly
comparable with our small replay. No public trained HTMA checkpoint was verified.

### SHuBERT is an appearance-based research option with more integration work

[SHuBERT, ACL 2025](https://aclanthology.org/2025.acl-long.1397/), learns from
approximately 1,000 hours of ASL. Its
[repository](https://github.com/ShesterG/SHuBERT) links weights and inference
instructions. The [quickstart](https://github.com/ShesterG/SHuBERT/blob/main/QUICKSTART.md)
requires signer cropping, pose extraction, face/hand cropping, separate DINO
features and SHuBERT inference across several environments. The README's
downstream fine-tuning section remains marked TODO.

It is worth considering if pose loses discriminating visual information.
Its ASL results do not establish ISL transfer, and the added pipeline makes it a
less economical first challenger than SignCLIP for this local prototype.

## Focused next experiment

1. Verify sign forms and tracking on fresh recordings from the seated setup.
2. Use five supported ISL concepts initially. Build a small reference bank, starting
   with roughly 3–5 correctly labeled examples per concept. This is an enrollment
   budget for an experiment, not a proven sample requirement.
3. Keep reference, threshold-calibration, and test recordings in separate capture
   sessions. Retain existing footage as development evidence; do not turn it into
   a new acceptance set.
4. Embed references and queries with SignCLIP's documented preprocessing. Compare
   nearest-example recognition with an equivalent SL-GCN feature baseline.
   Compare the same concepts, references and queries; do not compare unrelated
   headline benchmark percentages.
5. Calibrate abstention using unsupported signs, transitions and idle footage.
   Nearest-neighbor lookup always has a nearest example, even for nonsense input.
   Report correct accepted outputs, wrong accepted outputs, coverage and latency.
6. If same-sign clips consistently match their references across sessions, consider
   a small classifier or limited fine-tuning. If not, inspect tracking and
   representation errors before investing in a larger training run.

Public data can supply pretraining and verified references. The scarce resource
is representative labeled data from our signer, camera, framing and interaction.
Augmentations and dataset mirrors do not add independent real-world evidence.

Keep sentence composition constrained to recognized concepts and explicit intent,
with exact preview/edit/approval. The known “today” meaning error is unresolved.
Bolna speech and injection into the existing user-started call remain independent
feasibility gates. This research does not authorize training, installs or calls.
