# ISL recognition: what the research means for Ishara

Research date: 20 October 2026.

The strongest direction for Ishara is a pretrained temporal sign representation
with consistent body normalization, reliable hand tracking, and explicit rejection
of unsupported input. OpenHands is a useful concrete starting point for that
direction. SignCLIP provides a second route based on reference examples. RGB video
models offer complementary information when landmarks lose important hand detail.

There are also genuine downloadable ISL sentence models. Their published evidence
does not yet support selecting one for our appointment-call demo.

This is a research recommendation, not a selected production architecture.
No new model inference, training, webcam tests, or paid service calls occurred.
The [source audit](source-audit.md) records
the inspected files, revisions, reported results, access limits, and licenses.

## First, separate the tasks hidden behind “ISL detection”

The listings on Hugging Face and Kaggle solve different problems:

1. **Alphabet classification:** one image becomes a letter or digit.
   It can support spelling, but it does not capture the movement of a word sign.
2. **Isolated recognition:** a clip containing one sign becomes a class label.
   INCLUDE and most OpenHands checkpoints solve this task.
3. **Sign spotting:** a system finds whether, or where, a particular sign occurs
   inside a longer sequence. This needs evidence beyond isolated classification.
4. **Continuous recognition:** uninterrupted signing becomes a sequence of glosses.
   A gloss is an annotation for a sign, not necessarily an English word.
5. **Translation:** signing becomes a sentence in another language, with meaning,
   grammar, spatial references, and nonmanual information preserved.

A camera loop around an isolated classifier does not automatically solve the last
three tasks. Likewise, fluent English produced from incorrect labels can hide a
recognition error. ISL is a language with its own grammar and regional variation.

For Ishara, a bounded set of recognized meanings is a plausible hackathon scope.
Calling that unrestricted ISL translation would overstate the evidence.

## What our webcam failures tell us

The recorded observations remain: 10/11 selected INCLUDE dataset clips classified
correctly, while seven intended-hello segments from two webcam sessions did not.
The second session captured about 30 frames per second.

I previously overstated the diagnosis when I said the remaining problem was
physical framing and that a standing test would settle feasibility. Those were
hypotheses. Neither the gesture's linguistic correctness nor a single root cause
was established.

Possible causes include camera scale, missing hands, hand-slot swaps, tracking
errors, legacy preprocessing differences, sign boundaries, and temporal sampling.
A trained classifier can also fail on a new signer despite all software behaving
as intended.

The selected dataset clips were reused while changing normalization and
segmentation. They are now development examples for our adapted pipeline.
Their score cannot establish exact upstream equivalence or unseen-camera accuracy.
The recorded failures also do not prove INCLUDE is universally unusable.

## The techniques that matter

### 1. Normalize the representation during training and inference

Raw image coordinates encode where the person sits in the frame. A useful pose
representation can subtract a shoulder/body reference and divide by body scale.
This reduces sensitivity to camera distance and translation.

Hand-local coordinates can preserve finger shape, while body-relative hand
positions retain where the sign is articulated. Removing all body context can
make signs at the forehead and chest indistinguishable.

[OpenHands](https://aclanthology.org/2022.acl-long.150/) publishes INCLUDE
configurations that apply shoulder-based centering and scaling during both
training and validation. Its graph model represents relationships between joints.
Its DPC variant learns temporal features from a large unlabeled signing corpus.

That is a more principled lead than adding normalization to our existing raw-coordinate
checkpoint. A new transform at inference can move inputs away from what that
checkpoint learned. Eleven successful reused clips do not establish its safety.

**Implication:** prefer a checkpoint with a documented input contract that already
matches the intended representation. Normalization cannot recover an occluded hand
or guarantee robustness to a new camera angle.

### 2. Treat landmark quality as part of the model

MediaPipe detects geometry; it does not understand signing.
Overlapping hands, hands against the face, fast motion, and side-facing fingers
can produce missing or inaccurate points.

[Roh et al.](https://aclanthology.org/2024.signlang-1.36/) study anchor normalization
and reconstruction of missing hand points. Their reported improvement is on
WLASL-100, an ASL benchmark. A [2026 estimator comparison](https://aclanthology.org/2026.signlang-1.39/)
shows that the pose extractor changes downstream translation quality on German
signing. These are methodological lessons, not ISL performance guarantees.

A suitable future pipeline would preserve detection confidence and distinguish
missing measurements from real zeros. It would track hand identity across time,
interpolate only short gaps, and avoid fabricating long missing movements.
Heavy smoothing can remove meaningful finger motion.

**Implication:** a larger classifier cannot recover information that its input
representation discarded. Changing the landmark extractor also changes the input
distribution, so it needs compatible preprocessing and often adaptation.

### 3. Model movement, not just a succession of pictures

LSTMs and GRUs summarize sequences. Temporal convolutions detect local motion.
Transformers connect more distant frames. Graph networks model joint relationships
over time. None is automatically superior without comparable data and evaluation.

The [2026 HTMA paper](https://openaccess.thecvf.com/content/CVPR2026W/MSLR/html/Varanasi_Isolated_Sign_Language_Recognition_via_MediaPipe_Landmarks_A_Case_Study_CVPRW_2026_paper.html)
combines normalized hand/body landmarks, local temporal convolutions, and attention.
It pretrains on larger ASL resources before adapting the classifier to ISL.

Two translation studies explicitly add motion:

- [SpaMo-OF](https://aclanthology.org/2025.wslp-main.7/) combines spatial features
  with optical flow and video features.
- [iSign T5 motion](https://arxiv.org/abs/2609.12993) adds frame-to-frame differences
  to pose features before projecting them into a language model.

Both support studying motion features. They do not prove that every model benefits:
SpaMo-OF's optical-flow addition reduced its reported result on a different dataset.

**Implication:** preserve timestamps, sampling rate, and complete meaningful motion.
Frame differences depend on frame rate. Aggressive subsampling can remove the exact
finger movement that distinguishes two signs.

### 4. Reuse sign-specific representations

Transfer learning means reusing features learned from other examples.
It does not mean an ASL label map recognizes the corresponding ISL signs.

Three relevant approaches are:

- **OpenHands DPC:** learn temporal structure from unlabeled signing, then adapt to
  a labeled vocabulary.
- **CISLR prototypes:** represent clips with pretrained video features and compare
  an input with labeled reference examples.
- **SignCLIP:** learn a shared embedding space for signing and text through
  contrastive learning, then use reference examples or adapt to a new task.

[SignCLIP](https://arxiv.org/html/2407.01264v2) is particularly relevant:
its published language inventory includes 6,086 ISL dictionary entries.
Its paper still stresses adaptation for inputs outside its training distribution.
Exposure to ISL is stronger evidence than ASL-only training, but it is not a
demonstrated appointment recognizer.

[SHuBERT](https://aclanthology.org/2025.acl-long.1397/) extends this principle through
self-supervised learning across hand, face, and body streams. Its demonstrated
results concern ASL; ISL transfer remains an engineering question.

**Implication:** if later adaptation is needed, reuse a suitable encoder and adapt
a small part before considering training a whole network. A prototype approach
can avoid new neural training, but still requires representative reference data.

### 5. Combine complementary information only when it helps

The user's idea of “combining forces” has three distinct forms:

- **Feature fusion:** one system combines pose with video pixels.
- **Ensembling:** independently trained predictors combine their outputs.
- **Cascading:** a cheap first stage asks a second model only when needed.

Pose reduces background variation and input size. RGB retains hand appearance,
contact, and facial details that sparse landmarks can miss.
[Uni-Sign](https://arxiv.org/abs/2501.15187) demonstrates pose/RGB fusion with
confidence-aware sampling. Its main pretraining is Chinese Sign Language.
[SignLink-ISL](https://github.com/Naneet/SignLink-ISL) provides a simpler RGB
R3D-18 approach trained on INCLUDE.

Three INCLUDE models can share the same blind spots. Majority voting does not
fix missing visual evidence, and choosing the highest confidence across models
is invalid without comparable calibration.

**Implication:** if fusion later becomes necessary, pose plus RGB is a stronger
hypothesis than collecting many similar checkpoints. A pretrained classifier
cannot accept a new feature stream without an appropriate fusion method.

### 6. Separate sign boundaries from sign identity

Our current hands-up/hands-down segmenter is a diagnostic convenience.
Natural signing does not require hands to return to the hips between words.
Signs blend into one another, and meaningful pauses can happen with hands raised.

For an initial bounded interaction, an explicit start/end action can isolate
recognition quality. A natural interface requires a separate sign-activity or
boundary model, or a continuous sequence model.

CTC is one method for learning an alignment from frames to ordered gloss labels.
It does not provide translation grammar, an unsupported-sign guarantee, or usable
streaming behavior simply by being added to an isolated checkpoint.
[Sign spotting research](https://link.springer.com/article/10.1007/s11263-022-01589-6)
also shows that locating a dictionary sign in continuous signing is its own problem.

**Implication:** keep segmentation and recognition as separate uncertainties.
Do not make a standing, hands-at-hips ritual a presumed linguistic requirement.

### 7. Build abstention into the decision

A closed vocabulary classifier always has a winning class. A probability of 0.88
for “orange” does not mean the input is supported or correct.
Adding a negative class helps only for the negatives represented during training.

A future acceptance decision can consider input quality, sign activity, calibrated
class scores, distance to reference examples, and stability over time.
Each mechanism still requires data from unsupported signs and ordinary movement.
Temporal consistency alone can stabilize a wrong answer.

Measure both how often the system accepts an input and how often accepted inputs
are wrong. A system that rejects everything has low false acceptance but no utility.

**Implication:** keep recognized text subject to user confirmation before speech.
An LLM can format approved meaning, but it cannot infer a missing date, negation,
or intention from a weak visual guess.

## What the datasets contribute

**INCLUDE: a small repeated-word benchmark.** Its released 4,292 videos cover 263
signs. It is useful for isolated classification and reproducible comparisons.
Kaggle crops, landmarks, and augmented copies remain the same source recordings.

**CISLR: vocabulary breadth.** It reports 7,050 clips across 4,765 words and 71
signers. That is roughly 1.5 clips per word on average. The diversity is useful,
but the sparse examples motivate prototype learning rather than treating it as a
large, well-covered supervised corpus.

**ISLRTC and bridgeconn: reference signs.** Dictionaries help identify vocabulary
and signing variants. bridgeconn supplies video plus two pose representations for
3,077 lexical items. Dictionary explanations may need trimming before they become
single-sign references.

**ISL-CSLTR: controlled sentence examples.** The original release reports 700
videos for 100 sentences. This can support a bounded phrase study. A classifier
that memorizes those sentence identities has not learned unrestricted translation.

**ISLTranslate and iSign: sentence research.** Their roughly 31,000 and 118,000+
reported pairs support alignment and translation research. Some annotation comes
from semi-automatic alignment; source provenance and sampled human validation
matter. Different releases and derivatives have different totals.

**GloSL-ISL: convenient harmonization.** This packages related pose/text data and
documents source-video-grouped splits. It is not independent additional training
data. Its card reports a severe source overlap in an earlier row-based split.

**Kaggle character datasets: a different output task.** They can help a deliberate
spelling feature. They do not provide motion supervision for appointment meanings.
The user's specific CSV listing needs schema and license clarification.

Licensing also differs. INCLUDE declares CC-BY-4.0; iSign declares noncommercial
share-alike terms; bridgeconn declares CC-BY-SA-4.0. CISLR's HF metadata conflicts
with its README. A mirror's MIT badge does not automatically relicense source video.
The audit preserves these distinctions rather than assuming everything public is
interchangeable.

## Which released artifacts deserve attention

**Highest priority for a bounded recognizer: OpenHands DPC / SL-GCN.**
There are published INCLUDE checkpoint bundles, explicit normalized pose configs,
and a sign-specific training method. The tradeoffs are old dependencies, reduced
landmark detail, and continued dependence on INCLUDE's vocabulary and domain.
This is a source-based preference, not a measured winner on our footage.

**Most useful alternative direction: SignCLIP plus verified ISL references.**
It offers a broader representation and a way to cover meanings through examples.
Reference selection, licensing, rejection, and adaptation remain substantial work.
Dictionary retrieval can succeed without generalizing to live signing.

**Most useful complementary input: an RGB temporal model.**
SignLink's R3D-18 is a concrete lead. Its reported 89.51% is not comparable with
our 11-clip check, nor proof of better webcam behavior. It shares INCLUDE's source
limitations and requires review of label order and preprocessing.

**A genuine sentence-model lead: iSign T5-small-motion.**
The public repository includes trained weights and inference code, around 243 MB
for the small model plus pose encoder. This corrects an overly broad claim that
ISL sentence checkpoints do not exist.

However, its paper reports BLEU improving from **0.189 to 0.298**, on its internal
split. The public evaluator uses SacreBLEU's 0–100 score; these are not 18.9 and 29.8.
Its source split is random by row, and training budgets differ between model sizes.
The paper separately reports fifth place on an official test leaderboard.
The authors explicitly describe the models as research baselines.

**Useful ideas, higher adaptation cost: Uni-Sign, SHuBERT, HTMA, SpaMo-OF.**
These motivate fusion, sign-specific pretraining, temporal modeling, and motion.
Their languages, artifact availability, resource needs, and evaluation conditions
prevent treating them as interchangeable drop-in ISL solutions.

**Lower relevance despite attractive names or scores:**

- Hemg's 99.05% card score belongs to 35 letter/digit image classes.
- The “Hindi Sign Language Detection” model predicts 29 Devanagari characters.
- MAEFORMER's released checkpoint predicts eight specific isolated signs.
- cdsteameight publishes a real Keras artifact, but its limited documentation and
  training log do not establish a strong sentence translator.
- Abs6187's root metadata and broader model-card claims need reconciliation.
- signBridge's checkpoint is gated.

General video models such as Gemini or Jev remain possible research comparators.
Generic video understanding is not evidence of ISL understanding. The HTMA study's
poor VLM results concern its tested models, so they neither prove nor disprove
those particular services. Google SL2T's current consumer rollout is ASL on Pixel;
no usable public ISL/iPhone integration was established.

## How to read the accuracy claims

The HTMA paper reports **95.88%** on the original INCLUDE split and **83.82%** on
a stricter split. The stricter method approximates signer groups from recording
IDs, so its protection is incomplete. The difference still demonstrates why split
design changes the apparent result.

Scores should be compared only when language, class inventory, source data, split,
metric, and evaluation procedure match. A 35-letter result, 263-sign result,
few-shot retrieval result, and sentence BLEU score answer different questions.

There are several distinct leakage risks:

- Frames from one clip divided between training and evaluation.
- Augmented copies of one source recording divided between them.
- Multiple sentence segments from one source video divided between them.
- The same signers appearing on both sides of a claimed new-signer evaluation.
- Using the test set repeatedly to select preprocessing, thresholds, or checkpoints.

For a later Ishara comparison, the existing recordings belong in development.
Fresh sessions under the intended seated setup would be needed for a final check.
If new signers are a requirement, evaluation must hold out signer identities too.

Useful measures include per-meaning recognition, accepted-output error, abstention
rate, wrong emissions per minute of idle activity, repeated outputs, and measured
sign-end-to-text latency. Translation additionally needs human assessment of meaning,
especially negation, dates, names, and omitted information. Ten attempts can guide a
hackathon decision but cannot establish reliability with statistical confidence.

## Recommendation at this checkpoint

Keep the current recognizer as a recorded baseline. Stop treating additional
normalization tweaks or another INCLUDE model as the default route to success.

For the bounded hackathon interaction, favor a temporal pose model trained with
consistent normalization. OpenHands provides the strongest concrete lead found
for that choice. Keep SignCLIP/reference matching as the main alternative.
Study RGB fusion as a response to demonstrated tracking failures, rather than
adding an ensemble before its benefit is known.

Keep sentence translation as a separate research route. The newer T5 release
makes that route concrete, but the current evidence gives no reason to make it the
demo dependency. PoseStitch's 3.43 BLEU-4 and SpaMo-OF's 8.58 on a selected subset
are likewise study-specific results, not comparable field-wide limits.

If all suitable pretrained routes eventually miss the intended camera domain,
limited adaptation of a pretrained encoder may be more productive than model
shopping. That would require representative, properly labeled ISL examples and
a fresh evaluation set. It is a later decision, not work started in this pass.

The key missing resource is trustworthy data for the intended interaction and
camera setup, with appropriate ISL expertise. More mirrored copies of the same
dataset cannot supply it. No Deaf-user or natural-conversation validation has
occurred. The Bolna and device-audio feasibility gates remain separate.
