# Handoff: a ready-made ASL recognizer in two days (26–27 Oct)

Written 25 October 2026 for the teammate. Supersedes the recognition track (R1–R4, G2)
of [PLAN.md](../../PLAN.md) for the demo; everything else in the plan (Bolna Path B,
composer, call safety, iPhone gates) stands. Decision D8 in the plan points here.

## The decision, in one paragraph

We will **not record our own signs and we will not train or fine-tune anything.** The
recognizer for the demo is a **published, signer-independent ASL model trained on public
data**, dropped into the existing landmark → segment → match → chip pipeline. The
presenter learns the script's signs from one canonical ASL source and signs live. ISL
stays the product goal; an **ISL-overlap test** (below) decides, by measurement and not by
belief, which of our ISL signs the ASL model already recognizes, so the presenter may sign
those the ISL way. Everything not covered by the model becomes a button. Nothing is spoken
without SEND, as before.

Why: public ISL data cannot give a signer-independent recognizer this week (INCLUDE has
~16 clips per word from a handful of students, and **no clips at all for yes, no, sorry**;
cross-signer SignCLIP accepted 4 of 42 public clips in
[video-pipeline-eval.md](../experiments/video-pipeline-eval.md)). Public ASL has ~94k
landmark sequences from 21 Deaf signers under CC-BY and a winning model with public
weights. Picking that up is a two-day job; closing the ISL data gap is not.

## What is already out there (checked 25 Oct)

| Asset | What it is | Terms | Evidence |
|---|---|---|---|
| **Google ASL Signs / PopSign corpus** ([Kaggle `asl-signs`](https://www.kaggle.com/competitions/asl-signs)) | ~94,477 isolated-sign sequences, **250 signs, 21 Deaf signers**, recorded on Pixel phones at home. Landmarks only: **MediaPipe Holistic 543 points × (x, y, z)**, the same extractor family we run. | **CC-BY 4.0** (Deaf Professional Arts Network and Georgia Tech, per the data card). Downloading needs a Kaggle account that accepted the competition rules. | Data card read 25 Oct. Not downloaded yet. |
| **1st-place model** (hoyso48) | 1D-CNN + Transformer, ~1.85M parameters, trained on all competition data. Author-reported **participant-split CV 0.80, private leaderboard 0.88** over 250 classes. Preprocessing (nose-centred normalization, selected landmarks, lag-1/lag-2 motion) is inside the exported model. | Code **MIT** ([GitHub](https://github.com/hoyso48/Google---Isolated-Sign-Language-Recognition-1st-place-solution)). Weights mirrored by the sign-language-processing group: [`sign/kaggle-asl-signs-1st-place`](https://huggingface.co/sign/kaggle-asl-signs-1st-place), `model.tflite` **11.2 MB** + `sign_to_prediction_index_map.json`. | Write-up and HF file list read 25 Oct. **Input/output signature not yet inspected**: competition format was `[frames, 543, 3]` float32 in, 250 probabilities out; confirm with the interpreter before anything else. |
| **SignCLIP-ASL** | The SignCLIP architecture we already run (609-feature Holistic input, Core ML conversion in `ml/coreml/`), **fine-tuned on PopSign + ASL Citizen + Sem-Lex (~200k examples)**. Covers glosses beyond the 250 (doctor, today, sorry, …) because ASL Citizen/Sem-Lex do. | Weights in the authors' [Drive folder](https://drive.google.com/drive/folders/10q7FxPlicrfwZn7_FgtNqKFDiAJi6CTc) ([README](https://github.com/J22Melody/fairseq/tree/main/examples/MMPT#demo-and-model-weights)); no explicit licence stated, same situation as the multilingual checkpoint we use. | README read 25 Oct; accuracy on these datasets is author-reported in their paper/CSV, not reproduced. Needs references or the text encoder (not instantiated in `signclip.py`). |
| OpenHands WLASL checkpoints | Pose SL-GCN/ST-GCN on WLASL-2000 (27 landmarks), `slgcn.py` already loads this family. | Apache-2.0 code; WLASL data terms separate. | [checkpoints.csv](https://github.com/AI4Bharat/OpenHands/blob/main/docs/_static/checkpoints.csv) lists `wlasl_slgcn.zip`. WLASL-2000 pose accuracy is low; **third choice only**. |
| ASL Citizen | 83k videos, 2,731 glosses, 52 signers. | Microsoft Research licence: non-commercial, no redistribution; 42.8 GB single zip. | **Not used.** Too big for two days and the licence is wrong for a product demo. |
| LiteRT for iOS | Runs `.tflite` in Swift: CocoaPods `TensorFlowLiteSwift` (optional `CoreML`/`Metal` subspecs). | Apache-2.0. | [Quickstart](https://ai.google.dev/edge/litert/ios/quickstart) read 25 Oct. Our app uses SwiftPM only; CocoaPods is new integration (Day 2, stretch). |

What we did **not** find: a public ISL model with signer-independent evidence; freely
downloadable BSL isolated-sign data (BSL-1K/BOBSL need research agreements); any Google
SL2T/SignGemma ISL release.

## Vocabulary: what the 250 signs give us

| Script word | In ASL Signs 250? | Plan |
|---|---|---|
| hello | yes | sign |
| thankyou | yes | sign |
| yes / no | yes | sign (hand forms); **also buttons**, as the plan already allows |
| tomorrow | yes | sign |
| morning | yes | sign |
| time | yes | sign (spare) |
| doctor | **no** | not needed: the call purpose `doctor_appointment` already carries it. Use **sick** (in the 250) for "I need to see a doctor" |
| today | **no** | **now** (in the 250) |
| evening | **no** | **night** (in the 250), spare |
| sorry, afternoon | **no** | drop; `sorry` can be a button if the script needs it |
| extras available | wait, please, later, yesterday, finish, callonphone, where, can | `wait`/`please` are useful spares |

Demo vocabulary (10, final list after Day 1): **hello, thankyou, yes, no, sick, tomorrow,
morning, now, time, wait**. Script turns become T1 `hello · sick · tomorrow`, T3
`no · morning`, T5 `yes · thankyou`; the composer's purpose supplies "doctor". The
other 240 classes act as a built-in "something else" bucket, which is a real advantage
over reference matching: the model has a place to put non-vocabulary movement.

## The ISL-overlap test (how we "combine" ISL and ASL honestly)

We do not assume any ISL sign equals its ASL counterpart. We **measure** it: run the ISL
clips already on this Mac (INCLUDE clips under `spikes/recognition/artifacts/clips/`,
ISLRTC/Bridgeconn dictionary cuts under `artifacts/video_eval/` and
`artifacts/gemini_probe/`) through the ASL model. A word is **shared** only if the
ASL gloss with the same meaning is top-1 on **every** ISL clip of it with the calibrated
margin. Shared words may be signed the ISL way in the demo and are labelled so on the
slide; everything else is signed the ASL way. Expectation, not promise: `hello` and
possibly `time` pass; most others fail (the Gemini probe saw ISL `doctor` read as `time`).
If nothing passes, the demo is ASL-only and the slide says so.

## Day 1 (Mon 26 Oct): bake-off and a working Mac path

All on the Mac, no device, no paid calls. Keep every clip under the gitignored
`spikes/recognition/artifacts/`; commit only our own outputs under `docs/experiments/evidence/`.

1. **Fetch and inspect model A** (the 1st-place TFLite).
   `huggingface-cli download sign/kaggle-asl-signs-1st-place model.tflite sign_to_prediction_index_map.json`
   into `artifacts/asl_signs/`. Record SHA-256s. Load with the LiteRT/TensorFlow Lite
   Python interpreter, print input/output details. *Done:* a note in the bake-off record
   with the exact signature, dtype and whether variable frame count is accepted.
2. **Adapter** `spikes/recognition/asl_signs_model.py`: `Observation` frames (the
   543-point Holistic output `live_source.track` already yields) → `[T, 543, 3]` with NaN
   for missing points (that is how the training data encodes misses; check against the
   Kaggle parquet convention) → 250 probabilities → ranked `(gloss, p)`. Pad the segment
   0.5 s before/after like the PopSign recordings. Smoke it on the 2026-10-20 webcam
   sessions in `artifacts/sessions/` (intended `hello`): *Done:* `hello` appears in the
   top-3 on most of them, or a written reason why not (framing, landmark version).
3. **Test clips** (local only, `video_eval.py prepare` with a new spec):
   - ASL: 2–3 public tutorial clips per demo word from other signers (Lifeprint/ASL
     University, Signing Savvy, YouTube; standard licence, local evaluation only, record
     URL and terms in `sources.json` as before). Model A trained on every PopSign signer,
     so PopSign data cannot be its test set.
   - ISL overlap: the existing INCLUDE, ISLRTC and Bridgeconn cuts of the 12 ISL words.
   - Negatives: 20+ clips of idle sitting, fidgeting, drinking water, scratching, a
     half-sign. These are not sign data; record them yourself or cut them from the public
     clips' rest periods.
4. **Decision rule for A** in `recognition_data.decision` terms: restrict to the demo
   subset; accept when top-1 is in the subset, `p ≥ τ` and `p₁ − p₂ ≥ m`; **pick-one**
   when the top-2 are both in the subset and close; else `?`. Calibrate `τ, m` **per sign**
   on the ASL test clips + negatives with the existing zero-wrong-accept rule
   (`retrieval.calibrate_policy` logic; a probe-style policy file). Keep `data.QUALITY`
   tracking minimums.
5. **Model B, only if A disappoints** (A's top-1 under 70% on the ASL test clips):
   SignCLIP-ASL weights into `artifacts/signclip/`, `signclip.py` takes a checkpoint
   path + pinned SHA (keep the multilingual pin as default), references = 20 PopSign
   landmark sequences per demo word (`kaggle competitions download -c asl-signs -f
   train_landmark_files/<participant>/<sequence>.parquet`, chosen from `train.csv` so that
   reference participants ≠ any test participant), kNN over the existing `rank`. Then the
   same test. B's upside is on-device reuse (`ml/coreml/convert_signclip.py` and
   `SignMatcher.swift` need only new weights); its downside is unmeasured accuracy.
6. **Bake-off record** `docs/experiments/asl-model-bakeoff.md` + evidence folder: per
   word top-1/top-2, accepted/wrong/`?` at the frozen cut-offs, negatives accepted,
   latency per segment, the ISL-overlap table, SHA-256s, sources. Same leakage discipline
   as the earlier records (cut-offs frozen before test, labels only in the scorer).
7. **Mac path end to end**: winner wired into `live_source.py`/`mac_bridge.py` as a
   second `Matcher` (selected by flag), `scripts/sign_lab.sh` runs with the real composer.
   **Presenter live trial**: 10 attempts per script sign, hands down between signs, logged
   with `--log`. *Done:* the per-sign table from the log.

**Go/no-go at the end of Day 1** (presenter live trial, Mac): ≥ 6/10 correct chips per
script sign counting one-tap pick-one, **0 wrong auto-accepted chips, 0 auto-accepts on
negatives**. If a sign misses, swap it for an in-vocabulary synonym or a button; if three
or more script signs miss, run Day 2 in "pick-one always" mode (model proposes top-2, the
user taps) and say so on the slide.

## Day 2 (Tue 27 Oct): phone, UI, script, docs

1. **Composer and vocabulary**: new labels in `backend/app/protocol.py`, `validator.py`
   (`sick` → "not feeling well / unwell" must count as its meaning, no invented symptom),
   `templates.py`; `ios/Packages/CallSession/.../Vocabulary.swift`,
   `RecognitionCore/.../SignLabel.swift`, `spikes/recognition/recognition_data.VOCABULARY`
   and the Sign Lab guides. Re-run the 813 backend tests and the Swift packages. Also fix
   issue #34 while in the validator.
2. **UI**: pick-one chips (two tappable candidates, nothing auto-selected), yes/no (and
   wait) buttons on the call screen; `?` stays `?`. Transcript and SEND semantics unchanged.
3. **On device**, pick by winner:
   - A: LiteRT via CocoaPods (`TensorFlowLiteSwift`, Metal subspec optional) wrapped in
     a `SignPipeline` encoder; the Tasks Holistic Landmarker output must be mapped to the
     same 543-point order. **Stretch.** If it slips, the demo runs recognition on the Mac
     bridge (PLAN D6 backup, G3 fallback) and the pitch says "designed for on-device".
   - B: re-run `ml/coreml/convert_signclip.py` + `parity.py` with the new checkpoint
     (expect the same `.cpuAndGPU` requirement), new bundle, no Swift changes beyond labels.
   Either way: **parity on the same clips, Mac vs phone**, before trusting phone chips.
4. **Script and rehearsal**: update PLAN §1 script to the 10-word vocabulary; two full
   run-throughs in Sign Lab; the presenter practises from one source only (PopSign's
   reference videos or Lifeprint), because the model learned the PopSign signers' forms.
5. **Docs**: PLAN §5/§6/§7 to match, `docs/HANDOFF.md`, `README.md`, ledger rows
   (below), status snapshot. Credit Deaf Professional Arts Network, Georgia Tech, hoyso48,
   the sign-language-processing mirror, and SignCLIP's authors if B is used.
6. **Still owed from the plan, not part of this track**: the first real Bolna call (V4,
   needs the founder's go-ahead and cost heads-up), iPhone install (Thu), G3/G4.

## Rules for this track

- **No training, no fine-tuning, no ASL Citizen download, no Gemini in the call path.**
  If a model needs a weight change to work, it is the wrong model for this week.
- Public clips are fetched for local evaluation only; nothing third-party is committed or
  put in the submission. Cut-offs are frozen before test clips run.
- A wrong word is worse than no word: auto-accept stays at zero wrong on everything we
  measure; uncertainty shows as pick-one or `?`.
- Wording for the pitch, every time: *"signer-independent ASL model from public data
  (21 Deaf signers); the presenter is hearing and learned the signs from PopSign; ISL is
  the goal and is blocked by data, which is the problem we want to solve; ISL forms are
  used only where we measured the model recognizes them; nothing is spoken without SEND;
  no Deaf-user validation yet."*

## Open questions for you (teammate)

1. Does the TFLite accept a variable frame count, or is it fixed to the competition's
   padding? Decides whether we resample segments.
2. Are PopSign landmark misses NaN or zero in the parquet files? Our `signclip_features`
   uses zeros for SignCLIP; model A must get what it was trained on.
3. CocoaPods in the iOS project: acceptable, or do we keep A on the Mac bridge for the
   demo and do on-device after the buildathon?
4. If B is tested: Kaggle account for the landmark files (competition rules acceptance is
   personal; do not share the token).

## Claim ledger

Rows R18–R23 in [CLAIM-LEDGER.md](../CLAIM-LEDGER.md#recognition-data-and-decision-models)
hold the sources behind this document and their evidence limits: ASL Signs corpus and
CC-BY (R18), the 1st-place model (R19), SignCLIP-ASL (R20), LiteRT on iOS (R21), ASL
Citizen not used (R22), and "ISL and ASL overlap" as a per-word hypothesis (R23).
