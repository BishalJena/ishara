# ISL recognition: source and artifact audit

Checked 20 October 2026. This pass studies methods, papers, datasets, and released
artifacts. It does not run models, train models, upload signing footage, or resume
the paused webcam tests.

The starting inventory is the user's `research-links.md`. Additional searches used
Exa. Hugging Face metadata and small configuration files were read through public
HTTP endpoints. GitHub source files and release metadata were also inspected.
Context7 supplied current Hugging Face Hub inspection documentation.

Evidence labels used here:

- **Inspected:** a primary page, configuration, source file, or public metadata.
- **Reported:** a result published by an author, not reproduced in this pass.
- **Hypothesis:** an engineering interpretation that needs future evidence.
- **Unresolved:** access, provenance, compatibility, or evaluation remains unclear.

## Released models

### AI4Bharat OpenHands

- [Paper, ACL 2022](https://aclanthology.org/2022.acl-long.150/)
- [Paper PDF](https://aclanthology.org/2022.acl-long.150.pdf)
- [Repository](https://github.com/AI4Bharat/OpenHands)
- Inspected source revision: `b9ccf9eaf2a71301fc4601a64a6af06fdef04c9b`.
- Code license: Apache-2.0. Dataset and checkpoint terms require separate attention.
- The repository states that it is no longer actively maintained.

**Technique:** pose sequences with BiLSTM, BERT, ST-GCN, or SL-GCN. Graph models
represent joints and their connections explicitly. Dense Predictive Coding (DPC)
adds self-supervised temporal pretraining before supervised recognition.

The paper reports 1,129 hours of unlabeled Indian signing for pretraining.
Its released models cover several sign languages. This is evidence for transferring
visual representations, not for treating different sign languages as interchangeable.

The [INCLUDE SL-GCN configuration](https://github.com/AI4Bharat/OpenHands/blob/b9ccf9eaf2a71301fc4601a64a6af06fdef04c9b/examples/configs/include/decoupled_gcn.yaml)
uses `mediapipe_holistic_minimal_27`, then `CenterAndScaleNormalize` with shoulder
references. Training adds shear and rotation. Validation uses the same normalization.
The [DPC fine-tuning configuration](https://github.com/AI4Bharat/OpenHands/blob/b9ccf9eaf2a71301fc4601a64a6af06fdef04c9b/examples/configs/include/pose_finetune_dpc.yaml)
also uses shoulder normalization.

This is materially different from applying a new coordinate transform to a model
trained on raw screen positions. It makes OpenHands a stronger conceptual candidate
for camera-position variation. It does not establish seated webcam accuracy.

**Implementation selection after the user's backend clarification:** prioritize the
published INCLUDE SL-GCN route for the first implementation. Reinspection of
[`PoseSelect`](https://github.com/AI4Bharat/OpenHands/blob/b9ccf9eaf2a71301fc4601a64a6af06fdef04c9b/openhands/datasets/pose_transforms.py)
confirms that the minimal 27-point preset selects upper-body and hand landmarks and
excludes pose hip indices 23/24. The shoulder references are indices 3/4 within the
selected representation. Thus the classifier's input contract does not itself
require hip coordinates. This does not prove the extractor, model, or segmenter will
work with our seated footage. The existing harness's hip-based boundary rule should
not be mistaken for an unavoidable requirement of this candidate.

The [release](https://github.com/AI4Bharat/OpenHands/releases/tag/checkpoints_v1)
lists these archive sizes, read from GitHub metadata:

- INCLUDE DPC: 35,639,064 bytes.
- INCLUDE SL-GCN: 40,608,718 bytes.
- INCLUDE ST-GCN: 32,294,362 bytes.
- INCLUDE BERT: 41,953,495 bytes.
- INCLUDE LSTM: 18,777,287 bytes.
- INCLUDE metadata: 47,041 bytes.

These are archive sizes, not RAM requirements or measured inference latency.
The configs use the published test split as the validation set for checkpoint
selection. Do not describe that as a fresh deployment test.

### SignLink-ISL

- [Repository and reported results](https://github.com/Naneet/SignLink-ISL)
- Inspected revision: `86cd45717464fd3f6118f5b0c77c58e2d0fec8ee`.
- Repository license: CC0-1.0. The underlying INCLUDE dataset has its own license.
- [Weight manifest](https://github.com/Naneet/SignLink-ISL/blob/86cd45717464fd3f6118f5b0c77c58e2d0fec8ee/models/pre_trained_models.json)
- [RGB model](https://github.com/Naneet/SignLink-ISL/blob/86cd45717464fd3f6118f5b0c77c58e2d0fec8ee/models/Conv3D.py)

**Technique:** pretrained R3D-18, a 3D convolutional network, followed by a sign
classification layer. It consumes video pixels rather than relying entirely on
extracted landmarks. The project also studies ResNet plus GRU and a landmark transformer.

The README reports 89.51% on complete INCLUDE and 54.55% for its landmark transformer
on a custom 50-word subset. The custom subset is not necessarily official INCLUDE-50.
Complete-dataset preprocessing uses 24 frames and spatial augmentations.

The manifest links a complete-INCLUDE checkpoint and several subset checkpoints
through Google Drive. The links are published; successful weight loading was not
checked. The training notebook evaluates the set named “test” during training.
The reported score therefore needs split and selection review before comparison.

**Use:** a complementary RGB method to understand alongside pose models. Its strength
is access to visual hand shape that a landmark extractor can lose. Its risks include
background shortcuts, larger input cost, and the same underlying INCLUDE domain.

### cdsteameight/ISL-SignLanguageTranslation

- [Model](https://huggingface.co/cdsteameight/ISL-SignLanguageTranslation)
- Inspected revision: `f66970dd8e899dbc8ece6d8b2ab16f2f535785cb`.
- Public, ungated. Model-card license: MIT.
- Actual file: `isl-translate-v1.keras`, 252,571,134 bytes.
- The short card identifies INCLUDE as its training data.

The repository has no standalone `config.json` or label map in the inspected listing.
The public [training log](https://huggingface.co/cdsteameight/ISL-SignLanguageTranslation/blob/main/runs/run_2024_04_30-18_46_12/csv.log)
contains validation accuracy peaking around 46.74% and ending around 46.23%.
These are logged training metrics, not an independently verified test score.

**Interpretation:** a real trained artifact exists, but the word “Translation” in
the name does not establish sentence translation. Architecture details, label order,
input processing, and the relationship between the log and saved checkpoint remain
unresolved.

### MAEFORMER / Shruti-Drishti

- [Model](https://huggingface.co/bhaswata08/MAEFORMER)
- [Project](https://github.com/pranjalkar99/shruti-drishti)
- Model revision: `e84f60a5c341c24e7de4d494d96dfcca52f411d1`.
- Project revision: `7946e2bb38ca7280fcb543e7a625106794938d1a`.
- Public safetensors file: 344,955,832 bytes.
- No model-card license was declared in the inspected metadata.

**Technique:** VideoMAE video transformer. Masked-video pretraining supplies a
general visual representation, followed by supervised sign classification.
The released configuration expects 16 frames at 224×224.

The actual `id2label` has **eight classes**: Beautiful, Blind, Deaf, Ugly, happy,
loud, quiet, sad. It is not a general 263-sign translator.
The broader project also contains smaller Keras/LSTM artifacts. Do not attribute
the capabilities of one project component to another checkpoint.

### Hemg/Indian-sign-language-classification

- [Model](https://huggingface.co/Hemg/Indian-sign-language-classification)
- Revision: `c42565a110ea50e6dcc9efed5cfc65877adc2a91`.
- Public safetensors: 343,325,492 bytes. Card license: Apache-2.0.
- Architecture: `ViTForImageClassification`, 224×224 images.
- Config labels: **35 classes, A–Z and 1–9**.

The card reports 99.05% evaluation accuracy and calls its dataset unknown.
This is an alphabet/digit image classifier. It cannot recognize temporal word signs
merely by polling it on successive frames.

### prithivMLmods/Hindi-Sign-Language-Detection and SigLIP2

- [Classifier](https://huggingface.co/prithivMLmods/Hindi-Sign-Language-Detection)
- Revision: `bb0480b2f234e8e4925afe70a8e5941f1053cc73`.
- Public safetensors: 371,651,052 bytes. Card license: Apache-2.0.
- Config labels: **29 Devanagari characters**, not conversational ISL words.
- Card-reported accuracy: 94.25%.

The README's illustrative label map differs from the actual config at index 12:
the example shows ड, while the config shows ढ. Label mappings need inspection.

[SigLIP2](https://huggingface.co/google/siglip2-base-patch16-224) is a general
image/text representation model. Fine-tuning it for character images does not add
a temporal sign-language encoder or sentence translator.

### Abs6187 and DynamicIndianSignLanguageDetection

- [Model](https://huggingface.co/Abs6187/isl-models)
- Revision: `c669d5f3177ee57836223083d975829d56be28e7`.
- Card license: MIT. Public checkpoint/configuration files exist.
- Root config and metadata describe **eight classes**: Hospital, How Are You,
  Monday, Night, Shoe, Street, Thank You, Yellow.
- `best_model_new.pth`: 39,381,548 bytes.
- Additional gating and specialist checkpoints are also published.

**Technique claimed:** MobileNet visual features plus temporal pose features,
transformer encoders, gated fusion, and hierarchical specialist classification.
Root metadata lists 1,194 training and 137 validation samples. Broad model-card
claims about 60–80+ signs and 93.8% accuracy do not identify which released
checkpoint and split they describe.

The previously linked Abs6187 GitHub project was unavailable in earlier research.
This pass found [PranavAngrish/DynamicIndianSignLanguageDetection](https://github.com/PranavAngrish/DynamicIndianSignLanguageDetection),
revision `c736116984208cd1e19451e9349cc12b10af1088`, with corresponding architecture
source and checkpoint filenames. This improves discoverability, but does not prove
checkpoint compatibility or the reported metrics. Its inspected GitHub metadata
does not declare a license.

Do not conclude that every hierarchical checkpoint has only eight classes from the
root metadata alone. The component-specific mappings still need reconciliation.

### signBridge

- [Application](https://github.com/Uni-Creator/signBridge)
- [Model listing](https://huggingface.co/Creator-090/isl-swin3d-model)
- Model revision: `0dea8498b002acea1f01f2a65e0a5e747bfeb09d`.
- Gated model. Listed checkpoint: 227,921,863 bytes.
- Direct config access returned HTTP 401 in this pass.

Earlier source research recorded a 76-word Video Swin model and author-reported
66.84% top-1 on 187 samples. This is a lead for an RGB temporal approach, with
access, provenance, and evaluation still unresolved.

## Datasets and what they can actually supply

### INCLUDE

[Original record](https://zenodo.org/records/4010759): 4,292 released videos,
263 isolated word signs. The original paper counts 4,287; the record explains that
five videos were added. License: CC-BY-4.0.

It supplies repeated word examples, not naturally segmented conversation.
Many apparent alternative datasets and models reuse these same recordings.
Do not count a repackaging as independent evidence or additional signer diversity.

### CISLR

- [Paper](https://aclanthology.org/2022.emnlp-main.707/)
- [Repository](https://github.com/Exploration-Lab/CISLR)
- [Dataset](https://huggingface.co/datasets/Exploration-Lab/CISLR)
- HF revision: `feda67dd9368fec5f188fd4bd1917ea5c2803c7c`.
- 7,050 videos, 4,765 words, 71 signers reported in the literature.
- Inspected files include prototypes, test metadata, videos, and I3D features.
- HF access is gated.

**Technique:** one-shot prototype recognition using features transferred from ASL.
It addresses sparse examples per word through representation reuse and similarity.
A larger dictionary gives coverage, but only one or a few examples per word provide
weak coverage of camera conditions and signing variation.

**License conflict:** the HF YAML declares AFL-3.0, while the README and project
explicitly describe CC-BY-NC-4.0 for the data. Preserve the noncommercial constraint
pending clarification. A permissive code license does not resolve the data terms.

### iSign and ISLTranslate

- [iSign paper](https://aclanthology.org/2024.findings-acl.643/)
- [iSign project](https://exploration-lab.github.io/iSign/)
- [iSign dataset](https://huggingface.co/datasets/Exploration-Lab/iSign)
- [ISLTranslate paper](https://aclanthology.org/2023.findings-acl.665/)
- [ISLTranslate source](https://github.com/Exploration-Lab/ISLTranslate)

ISLTranslate reports about 31,000 video/text sentence or phrase pairs.
iSign reports over 118,000 and includes video-to-text, pose-to-text, generation,
word presence, and semantic tasks. These datasets overlap in provenance.

The iSign site describes validation of 593 sampled pairs by certified ISL signers.
That is not a claim that every automatically aligned example is manually verified.
The current dataset card recommends grouping rows by source-video ID when splitting.
Separate segments of one recording must not appear on both sides of evaluation.

iSign HF revision: `e4ee6c5f0d9dfcbc74205e3f1388ce94da26c298`.
Access: gated. YAML license: CC-BY-NC-SA-4.0; prose specifies research/noncommercial
use. All listed files total about 228 GB, including roughly 58 GB of video parts
and 170 GB of pose parts. These are source materials, not a ready webcam model.

### pedroodb/glosl-isl

- [Dataset](https://huggingface.co/datasets/pedroodb/glosl-isl)
- [Provenance and split card](https://huggingface.co/datasets/pedroodb/glosl-isl/blob/main/card.json)
- Revision: `745795543fef509799e7e72640f286605c2ec670`.
- Public metadata declares CC-BY-NC-4.0. Reconcile upstream share-alike terms.

This is harmonized ISLTranslate/iSign **pose and text** data, not a newly collected
independent dataset or trained model. The card reports 126,846 samples and 269.03
hours. It identifies 543 MediaPipe Holistic points and normalization at load time.

The current split groups source videos and stratifies topics. The card reports
that the previous row split had 98% of test clips sharing a source video with train.
This is a maintainer-reported diagnostic, not a newly reproduced measurement.
Source-video separation does not automatically establish signer separation.

The provenance note permits pose inclusion and excludes video/privacy-revealing
material; the card says videos are not hosted. Do not use this public derivative
as a way around the original dataset's terms or access conditions.

### bridgeconn/sign-dictionary-isl

- [Dataset](https://huggingface.co/datasets/bridgeconn/sign-dictionary-isl)
- Revision: `aa6f00a8352bbc56230242a920012a219a840d76`.
- 3,077 lexical items, about 2.5 hours, reported by the card.
- Seven tar shards total about 7.11 GB.
- CC-BY-SA-4.0 declared.

Each sample contains video, gloss metadata, DWPose coordinates, and MediaPipe pose.
This is useful for studying reference matching and comparing pose representations.
It does not itself supply a trained classifier or a held-out webcam benchmark.

### ISLRTC dictionary and the re-encoded mirror

- [Official dictionary resource](https://www.data.gov.in/resource/indian-sign-language-dictionary-till-january-2024)
- [Mirror](https://huggingface.co/datasets/silentone0725/Indian_Sign_Language_Data.gov_Rencoded)
- Mirror revision: `453d57a4f59a4962a5f68eda098672f6d57db947`.
- Listed files total about 77.98 GB. The card describes H.265 re-encoding.

Useful for word coverage and reference forms. Dictionary entries can include
explanations or variants rather than tightly trimmed single-sign examples.
The mirror's MIT declaration does not independently establish relicensing rights
over the source videos. Trace original permissions and annotations before reuse.

### Kaggle: user-supplied character dataset

[mrigaankjaswal/indian-sign-language-to-characters-dataset](https://www.kaggle.com/datasets/mrigaankjaswal/indian-sign-language-to-characters-dataset)
is listed by its owner's Kaggle profile as one CSV of about 4 MB.
The dataset page returned a frontend error through the research fetcher.
Its exact schema, class counts, provenance, and license were not verified.

The stated character task differs from moving word signs. Do not promote this
resource to a conversational ISL dataset on the basis of its title.

### Kaggle: ISL-CSLTR

- [Kaggle mirror](https://www.kaggle.com/datasets/drblack00/isl-csltr-indian-sign-language-dataset)
- [Original Mendeley release](https://data.mendeley.com/datasets/kcmpdxky7p/1)

The release reports 700 videos, 100 spoken-language sentences, seven signers,
18,863 sentence frames, and 1,036 word-level images. The description also says
two native signers plus four student volunteers, an unresolved count inconsistency.
**1,036 images is not evidence of 1,036 distinct word classes.**

This could support a controlled phrase task or boundary research. Recognition of
one of 100 rehearsed sentences does not demonstrate unrestricted translation.
Confirm original license terms and signer metadata before constructing a split.

### Kaggle: processed INCLUDE landmarks

[kaushikyh/indian-sign-language-words-with-landmarks](https://www.kaggle.com/datasets/kaushikyh/indian-sign-language-words-with-landmarks)
describes 32 frames, 224×224, at 10 fps, for ViViT preprocessing.
The card says 80 signs, while the visible explorer lists 76 directories.
Its declared license is CC-BY-SA-4.0.

This saves preprocessing work but retains INCLUDE's source limitations.
Its sampling and landmark conventions must match any model consuming it.

## Research methods worth carrying forward

### Preprocessing and tracking are model components

[Roh et al., 2024](https://aclanthology.org/2024.signlang-1.36/)
study body/hand anchor normalization, reconstruction of missing keypoints, and
sequence-length handling. They report a 6.05-point improvement and 83.26% on
**WLASL-100**, with augmentation. This is ASL evidence, not an ISL benchmark.

[O'Brien et al., 2026](https://aclanthology.org/2026.signlang-1.39/)
compare pose estimators with a controlled translation pipeline on German signing.
They report roughly 11.5 BLEU for SDPose/Sapiens versus roughly 10 for MediaPipe.
The useful conclusion is that estimator choice changes downstream performance.
The scores and hardware demands cannot be transferred directly to our Mac/ISL task.

[Hand ROI study, 2024](https://arxiv.org/html/2405.03545v2)
explains how MediaPipe Holistic's hand-region heuristic can fail for hand orientations
that differ from its assumptions. This is a reason to inspect tracking quality,
not evidence that every failed prediction needs a different classifier.

### HTMA: a recent specialized ISL architecture

- [CVPR Workshops 2026 paper](https://openaccess.thecvf.com/content/CVPR2026W/MSLR/html/Varanasi_Isolated_Sign_Language_Recognition_via_MediaPipe_Landmarks_A_Case_Study_CVPRW_2026_paper.html)
- [PDF](https://openaccess.thecvf.com/content/CVPR2026W/MSLR/papers/Varanasi_Isolated_Sign_Language_Recognition_via_MediaPipe_Landmarks_A_Case_Study_CVPRW_2026_paper.pdf)

The method uses 42 hand plus 23 upper-body landmarks, XYZ coordinates, z-score
normalization, local temporal convolutions, and head/token mixing attention.
It transfers from WLASL2000, MS-ASL, and ASL-Citizen, then fine-tunes on ISL.
The paper also studies missing-landmark robustness.

Author-reported results: 95.88% top-1 on the original INCLUDE split, 83.82% on its
stricter split, and 19.20% on CISLR. The stricter split approximates signer groups
from adjacent recording IDs; true signer identity labels were not available.
Treat it as a useful warning about leakage, not perfect signer-independent proof.

The best tested fine-tuned general VLM reached 32.24%; zero-shot performance was
reported near zero. This applies to the tested LLaVA/LLaVA-NeXT/SmolVLM setups.
It does not establish the performance of Gemini, Jev, or every future VLM.
No public trained HTMA checkpoint was verified in this search.

### SignCLIP: representations and reference retrieval

- [Paper](https://arxiv.org/html/2407.01264v2)
- [Code and model instructions](https://github.com/J22Melody/fairseq/tree/main/examples/MMPT)

SignCLIP aligns signing and text embeddings through contrastive learning.
Pretraining uses roughly 500,000 dictionary clips across up to 44 sign languages.
The paper emphasizes few-shot prompting or fine-tuning for out-of-domain tasks.

This supports a route based on a pretrained encoder plus verified reference
examples, rather than training a whole network. No ready ISL appointment model or
ISL deployment accuracy was established here. Shared English labels do not make
signs in different languages equivalent.

The repository's [language distribution file](https://github.com/J22Melody/fairseq/blob/main/examples/MMPT/data_stat_sp_lan_dis.csv)
includes **6,086 entries tagged `ins`**, the Indian Sign Language code.
Thus, this is more relevant than an encoder exposed only to ASL.
The published model instructions link multilingual weights and ASL/BSL/Suisse
variants. The listed ISL data count does not establish unseen-signer ISL accuracy.

### Uni-Sign: pose and RGB fusion at scale

- [ICLR 2025 paper](https://arxiv.org/abs/2501.15187)
- [Code](https://github.com/ZechengLi19/Uni-Sign)

Uni-Sign combines pose and selected RGB features through prior-guided fusion.
Confidence-aware sampling helps address inaccurate landmarks while controlling
visual processing cost. Its pretraining resource is CSL-News, with 1,985 hours of
**Chinese** Sign Language. The repository also lists ASL translation checkpoints.

This is useful architectural evidence for complementary modalities.
No ready Indian Sign Language checkpoint was verified. “CSL” here does not mean
continuous Indian Sign Language.

### PoseStitch-SLT: continuous translation remains a larger problem

- [EMNLP 2025 paper](https://aclanthology.org/2025.emnlp-main.698/)

The method uses linguistically informed templates to compose pose sequences for
pretraining, then trains a transformer encoder-decoder.
Reported iSign BLEU-4 improves from 0.55 to 3.43; How2Sign improves from 1.97 to 4.56.
BLEU-4 is a translation metric, not percent recognition accuracy.
These improvements do not establish useful open-ended appointment conversation.
Synthetic concatenation also does not reproduce all natural transitions or grammar.
This result is specific to that experiment, not a ceiling on current ISL translation.

### SpaMo-OF: explicit visual motion

- [WSLP 2025 paper](https://aclanthology.org/2025.wslp-main.7/)
- [Paper PDF](https://aclanthology.org/2025.wslp-main.7.pdf)
- [Linked project](https://github.com/Analroy/SpaMo-OF)

This approach combines CLIP spatial features, GMA optical flow, VideoMAE temporal
features, and a Flan-T5-XL language model with LoRA adaptation.
It reports BLEU-4 of 8.58 on a **selected iSign-10k subset**.
The subset filters sentence lengths and balances word frequencies.
The same motion addition reduces performance on Phoenix-14T in the reported study.

The result supports studying motion and data curation. It is not directly comparable
to full-iSign scores or to isolated recognition accuracy. Experiments used an A100;
local deployment cost and complete trained artifact availability were not established.

### iSign T5 pose-to-text: an actual newer sentence-model release

- [September 2026 preprint](https://arxiv.org/abs/2609.12993)
- [Paper PDF](https://arxiv.org/pdf/2609.12993)
- [Model repository](https://huggingface.co/manavdhamecha77/iSign-t5-pose-to-text)
- [Code repository](https://github.com/manavdhamecha77/Sign-Lang-Trans)
- HF revision: `80e60781f37f5c2720a7bc927398fdd9b0c32298`.
- GitHub revision: `8f38105a50151fdb854d182105a238ad188342a1`.

**Inspected:** six ungated trained T5 checkpoint directories, pose encoders, and
inference source. T5-small-motion contains 242,041,896 bytes of safetensors and a
1,144,463-byte pose encoder. No license is declared in the inspected model metadata.
The README names `t5-base-motion-v2`, while the inspected tree uses `t5-base-motion`.

**Technique:** 33 body plus 21 landmarks per hand, each with XYZ and confidence,
produce 300 features per frame. Motion variants concatenate consecutive-frame
differences to obtain 600 features. A small MLP projects these into T5 embeddings.
The pipeline applies per-sequence z-score normalization and pads/truncates to 500
frames. This is genuine pose-to-English generation, rather than alphabet recognition.

**Reported:** T5-small-motion improves BLEU from 0.189 to 0.298 on an internal
1,887-example split from 18,867 examples. The paper separately reports fifth place
on a WSLP 2026 test leaderboard with 5,334 examples. The paper's comparison table
does not report that official test score.

**Important metric distinction:** [evaluation code](https://github.com/manavdhamecha77/Sign-Lang-Trans/blob/8f38105a50151fdb854d182105a238ad188342a1/src/evaluate_all.py)
uses `BLEU().corpus_score(...).score`, with no division by 100.
[SacreBLEU](https://github.com/mjpost/sacrebleu) reports this score on the usual
0–100 scale. Do not turn 0.298 into 29.8 BLEU or call it percent translation accuracy.
The source code supports reading these as very low absolute scores.

**Evaluation limitation:** [split code](https://github.com/manavdhamecha77/Sign-Lang-Trans/blob/8f38105a50151fdb854d182105a238ad188342a1/src/split_data.py)
uses random `train_test_split` on rows. It does not enforce source-video or signer
separation. This is a leakage risk, not proof that a particular overlap occurred.
The paper also acknowledges unequal training budgets, one run per model, and no
human evaluation. Larger T5 variants therefore cannot be declared inherently worse.

The inference preprocessing normalizes each feature over the whole input sequence,
including confidence features. Consecutive-frame differences are frame-rate dependent.
These details matter for future adaptation; replacing them at inference would
change the trained input distribution.

**Use:** a concrete research reference for sentence-model architecture and
reproducibility. Its availability corrects any blanket claim that no downloadable
ISL sentence models exist. Its evidence does not support choosing it for live calls.

### SHuBERT: self-supervised sign representations

- [ACL 2025 paper](https://aclanthology.org/2025.acl-long.1397/)
- [Full text](https://arxiv.org/html/2411.16765v3)

SHuBERT learns contextual representations from about 1,000 hours of ASL.
It combines separate hand and face image features with body pose, then predicts
cluster assignments for masked time/channel regions.
It demonstrates why a sign-specific pretrained encoder can be more useful than a
generic image encoder. Its evaluated ASL transfer does not establish ISL performance.

### Continuous recognition and sign spotting

[GloFE, ACL 2023](https://aclanthology.org/2023.acl-long.722/)
explains the distinction between gloss supervision, temporal alignment, and
direct video-to-text translation. CTC can align frame sequences with ordered
gloss targets; it does not itself translate into a different spoken-language grammar.

[Dictionary sign spotting, IJCV 2022](https://link.springer.com/article/10.1007/s11263-022-01589-6)
studies finding an isolated reference sign inside continuous BSL footage, using
contrastive learning and multiple-instance learning.
[An ISL word-presence study, WSLP 2025](https://aclanthology.org/2025.wslp-main.10/)
reports 61.88% accuracy and 60.00% F1 for query-sign presence using pose sequences.
Presence detection is not temporal localization or full sentence translation.

### Google SL2T / SignGemma

- [Current primary announcement](https://deepmind.google/blog/putting-sign-language-ai-into-users-hands/)

The August 2026 announcement describes landmark-to-text translation trained on over
100,000 hours across more than 50 sign languages. Initial consumer support is
ASL-to-English on Pixel 11. It explicitly addresses streaming, non-signing inputs,
left-handed signing, and one-handed use.

This is evidence that broad data and deployment engineering matter.
It is not evidence of an available public ISL API, downloadable ISL checkpoint,
or iPhone integration. Similarly titled third-party “SignGemma ISL” papers must not
be treated as official Google releases.

## Corrections to our earlier interpretation

The recorded INCLUDE results remain useful: 10/11 selected dataset clips and 0/7
intended-hello webcam segments. They do not establish the following earlier claims:

- that our adapted preprocessing exactly reproduces the legacy pipeline;
- that distance, standing posture, or the signer's gesture is the proven cause;
- that a single standing test can settle general feasibility;
- that post-training normalization is safe because 11 reused examples still classify;
- that a 0.5 softmax threshold detects unknown signing reliably;
- that model-forward time measures live sign-end-to-text latency.

Those clips were repeatedly used to select normalization and segmentation behavior.
They are now development examples for this adapted system, not untouched test data.
Splicing another signer's rest frames is a synthetic diagnostic, not recognition
evidence. No qualified ISL assessment of the user's signing occurred.

Possible confounders include hand-slot ordering, tracking the wrong person, missing
landmarks, temporal resampling, truncation, detector-version changes, and camera
domain shift. Framing is one hypothesis among these.

The current task remains research. The next synthesis should choose a small number
of distinct methodological routes, not propose running every model found online.
