# A public ASL model, untouched, on ISL clips, Lifeprint ASL clips and the presenter

Executed 25 October 2026 on the development Mac. Three runs of the same model with no
training, fine-tuning, references or enrollment, to answer: **can a published,
signer-independent ASL recognizer carry the demo, and which of our ISL signs does it
already recognize?** [Evidence](evidence/asl-model-probe/README.md) ·
[Code](../../spikes/asl_probe/) · [Decision D8](../../PLAN.md#2-decisions) ·
[Handoff](../handoffs/2026-10-26-ready-made-asl-recognizer.md)

```
clip / webcam ─▶ legacy MediaPipe Holistic ─▶ [T, 543, 3] Kaggle layout (NaN = missing) ─▶ 1st-place TFLite ─▶ 250 logits ─▶ softmax
                                               face 468 · left hand 21 · pose 33 · right hand 21                      top-1 / p / margin
```

## Headline

- **The model, zero-shot, recognizes 6 of 11 Lifeprint ASL clips** from a signer it never saw
  (no 0.93, now 0.90, please 0.94, yes 0.72, tomorrow 0.70, wait 0.88 in a 2 s window) and
  **misses `morning` and `sick` with flat outputs** (max p ≤ 0.16).
- **On the presenter's first free-form webcam session (55 cuts), `yes`, `no`, `now`, `please`
  were recognized on the first attempt (0.91 / 0.64 / 0.93 / 0.95)**, `hello` 1 of 4 above 0.6,
  `tomorrow` top-1 on 17 of ~21 attempts but at p 0.30–0.66, `morning` once at 0.62,
  `time` and `sick` never. Chip latency after the hands rested: **0.43–0.50 s**.
- **ISL overlap, measured not assumed:** ISL `thankyou` is read as ASL `thankyou` on 7/8 clips
  (0.77–0.95), the ISL wave `hello` on 7/9 (ISLRTC and the presenter's October takes; INCLUDE's
  hello form 0/6), ISLRTC `yes` hand form 0.92; `time`, `morning`, `tomorrow`, `today`,
  `doctor`, `afternoon`, `evening`, `sorry` are not shared. Over the 7 words both languages
  name: 16/48 top-1. The demo is **pure ASL** (D8); this table is why.
- **It knows when it does not know.** Right answers come out at 0.5–0.95; signs the model has
  no class for come out flat (max p ≈ 0.03–0.2). At p ≥ 0.6 with the 9-word vocabulary there
  were **0 wrong accepts in 55 presenter cuts and 0 among 79 ISL clips**; confident wrong
  outputs (`mitten` 0.98, `see` 0.93, `arm` 0.81, `bye` 0.88) were all non-vocabulary glosses.
- **Model cost: 4 ms per sign** on the Mac CPU; 11.2 MB file. Frame rate 15–60 fps changes
  little. Test-time augmentation does not help. **Narrow portrait framing does hurt** when
  hands leave the frame (simulated: `no` 0.64 → 0.42, `tomorrow` median 0.36 → 0.17).

## The model

Kaggle "Google – Isolated Sign Language Recognition" 1st place (hoyso48): 1D-CNN + Transformer,
~1.85M parameters, trained on the ASL Signs / PopSign corpus (~94k sequences, **250 signs, 21 Deaf
signers, recorded on Pixel 4a front cameras**, CC-BY 4.0). Author-reported participant-split CV
0.80, private leaderboard 0.88. Code MIT; weights from the sign-language-processing mirror
[`sign/kaggle-asl-signs-1st-place`](https://huggingface.co/sign/kaggle-asl-signs-1st-place):
`model.tflite` SHA-256 `f55a2bb1…0bb7` (11,242,036 bytes), class map SHA-256 `1fe747c2…bf5d`.
Inspected signature: input `[-1, 543, 3]` float32 (variable frame count accepted), output
`[250]` logits; preprocessing (nose-centred normalization, landmark selection, lag-1/lag-2
motion) is inside the model. Ledger R18, R19.

Landmarks: legacy `mp.solutions.holistic` (MediaPipe 0.10.21, complexity 1, no refined face),
the Mac pipeline's extractor; rows ordered face, left hand, pose, right hand as in the Kaggle
parquet files; missing parts as NaN. The training data used MediaPipe 0.9.0.1 of the same
solution. The iOS Tasks Holistic Landmarker is a different model: parity on the phone is still
to be measured (PLAN P3).

## Run 1: ISL clips (overlap test)

79 clips: INCLUDE 6 per word for the 9 words it has (54, spread over file numbers), ISLRTC
dictionary entries for all 12 words incl. variants (17), the presenter's 8 October webcam
"hello" takes. Whole clip, no detector. Scored against the ASL gloss of the same meaning where
one exists.

| ISL sign | n | top-1 over 250 | top-5 | What happened |
|---|---:|---:|---:|---|
| thankyou | 8 | **7** | 7 | ISLRTC main sign 0.92; all 6 INCLUDE signers 0.77–0.95. "Sign 2" variant → `head` 0.29 |
| hello | 15 | **7** | 8 | ISLRTC 0.82; presenter's waves 6/8 (0.39–0.93; one → `thankyou` 0.57, one → `dad` 0.36); INCLUDE's hello form 0/6, all flat (≤ 0.13) |
| yes | 2 | 1 | 1 | ISLRTC hand form 0.92; "Sign 2" is head-only, no hands tracked |
| no | 2 | 1 | 1 | "Sign 2" → `no` 0.48; main sign → `bye` 0.88 |
| time | 7 | 0 | 2 | flat; `weus`/`shoe`/`arm` ≤ 0.20 |
| morning | 7 | 0 | 0 | flat; ISLRTC → `wet` 0.55 |
| tomorrow | 7 | 0 | 0 | flat; `jacket`/`vacuum` ≤ 0.15 |
| today, doctor, afternoon, evening, sorry | 31 | n/a | n/a | no ASL gloss in the 250; outputs flat (`vacuum`, `pool`, `clean`… ≤ 0.2) |
| **overlap words** | **48** | **16** | **19** | |

A deliberate trap, kept as a warning: restricting the softmax to the 10 demo glosses *before*
thresholding made ISL `time` → `time` 7/7 and `evening` → `no` 6/7, at p ≈ 0.01. **Never restrict
first**; threshold on the full output, then check the label is in the vocabulary.
A "portrait" variant (x rescaled to a 9:16 aspect) gave identical results: the model normalizes
per axis.

## Run 2: Lifeprint ASL clips (positive control)

Lifeprint (ASL University, Bill Vicars) per-word YouTube videos, downloaded at ≤ 480p for local
evaluation only; the page GIFs turned out to be 3–10 still frames and are not scorable.
`--window 2.0` scores sliding 2 s windows on clips longer than 2 s.

| Word | Clip | Whole clip | Best 2 s window |
|---|---|---|---|
| no | 2.9 s | **no 0.93** | 0.95 |
| now | 2.5 s | **now 0.90** | 0.92 |
| please | 2.4 s | **please 0.94** | 0.94 |
| yes | 2.0 s | **yes 0.72** | – |
| tomorrow | 2.6 s | **tomorrow 0.70** | 0.72 |
| tomorrow (2nd video) | 2.6 s | `every` 0.57, tomorrow 0.06 | ASL "every day" is TOMORROW repeated; likely a doubled variant, unverified |
| wait | 10.6 s lesson | wait 0.08 | **wait 0.88 at 3.5 s** |
| wait (2nd video) | 5.1 s | flat (`if` 0.09) | flat |
| morning | 2.2 s, 1.8 s | flat (`happy` 0.15; `table` 0.05) | flat |
| sick | 7.7 s lesson | flat (`if` 0.08) | `sad` 0.16 |

**6 of 11 right at 0.70–0.94; every miss except `every` is flat.** The open-set signature holds
on real ASL from a stranger.

## Run 3: the presenter, live, laptop webcam

`spikes/asl_probe/live_probe.py`: the existing start/stop detector (`detector.py`, 2 s rest
calibration, hands above the rest line start a sign, 0.4 s at rest ends it) cuts each sign; the
cut goes to the model whole. 55 cuts in one free-form session (the presenter went through the
lesson page in his own order, so **labels are inferred, not ground truth**; see the evidence
file). Decision shown: p ≥ 0.6, margin ≥ 0.3, gloss in the 11-word probe vocabulary.

| Word (inferred) | Attempts | Model | Read |
|---|---:|---|---|
| hello | 4 | 0.95, 0.24, 0.58, 0.37 | one clean wave; `pretend`/`hat` crept into the others |
| yes, no, now, please | 1 each | **0.91, 0.64, 0.93, 0.95** | first try |
| tomorrow | ~21 | top-1 on 17; p 0.30–0.66, median 0.36; runner-up `yourself`/`another`/`later` | consistent near-miss in form (below) |
| morning | ~5 | 0.22, **0.62**, else `look`/`closet` | recoverable |
| wait | ~7 | `see` 0.93, `find` 0.81, `drink` 0.71, `mitten` 0.98 | not read as wait; form unknown |
| time | ~6 | `arm` 0.80, `weus` 0.48 | same as the ISL `time` clips; dropped |
| sick | ~7 | `taste` 0.58, `go`, `wet` | hand at the chin, not the forehead; dropped |

Detector segments 1.0–1.9 s; latency hands-at-rest → chip **0.43–0.50 s**; hand tracking
0.75–1.00 of frames. Wrong accepts among vocabulary words at p ≥ 0.6: **0**. At p ≥ 0.5: one
(hello wave → `thankyou` 0.57).

### Why `tomorrow` sits at 0.4–0.5

Thumb-tip trajectory relative to the nose, in shoulder-widths (`offline_analysis.py` style check):

| | Closest approach to the face | Travel after contact | Clip |
|---|---|---|---|
| Lifeprint, 0.70 | 0.32 | **2.4 down/out** | 2.6 s |
| Presenter, 0.50–0.66 (6 cuts) | 0.26–0.40 | **0.0–0.3** | ~1.0 s |
| Presenter → `yourself` 0.84 | 0.31 | 1.2, but **forward from the chest** | |

Contact point right, arc missing or started from the wrong place (`yourself` is a thumb-up hand
pushed forward from the body). A coaching fix, not a model fix: touch the cheek, pause, arc
forward-and-down a forearm length, slower.

## Offline analysis on the 55 cuts

| Question | Result |
|---|---|
| Latency | 4.1 ms per cut; 7.8 ms with 6-way TTA (Mac CPU, XNNPACK) |
| Test-time augmentation (time crops ±15 %, scale ±7 %, hflip, averaged) | no gain: medians ±0.03, top-1 unchanged |
| Two consecutive attempts averaged | `tomorrow` median 0.36 → 0.32; form, not noise |
| Frame rate 15 / 60 fps (resampled) | essentially unchanged; `morning` 0.62 → 0.75 / 0.84 at 15 / 60 |
| Simulated 9:16 phone window (landmarks outside become NaN) | `no` 0.64 → 0.42, `tomorrow` 0.36 → 0.17, `morning` 0.62 → `tree`: **hands must stay in frame** on a phone |

## Run 4: the app's path in the simulator vs the Mac (27 Oct)

The same 18 Lifeprint clips (the YouTube ones re-encoded to H.264: the simulator can't decode
VP9), fed whole through both paths. **Mac:** legacy MediaPipe Holistic 0.10.21 → Kaggle layout →
`ai-edge-litert`. **App:** the Holistic Landmarker task the iPhone runs → `KaggleLayout` → LiteRT
2.17.0 on iOS (`SignPipelineLiteRT`), in the iOS simulator (`IsharaTests/ASLParityHarness`).
Compared by `spikes/asl_probe/parity.py`;
[evidence](evidence/asl-model-probe/parity-simulator-lifeprint.json).

| Measure | Result |
|---|---|
| Clips where the Mac is confident (p ≥ 0.6) | 9; the app gives the same top-1 on **9/9** and the same chip on 9/9 (no ×2, now ×2, tomorrow ×2, please, wait, yes) |
| Decision (chip / pick-one / `?`) under the bundle's rule | same on 17/18; the other is `yt_morning` 1: Mac `?` (happy 0.16), app pick-one MORNING 0.41 |
| Top-1 overall | same on 14/18; the 4 differences are all low-confidence clips that are `?` on both |
| Runtime | the Mac model on the app's own landmarks reproduces the app's probabilities exactly (max difference 0.0 at 5 decimals); a fixed input gives logits within 0.001 and the same top-5 (`SignPipelineLiteRT` test) |
| Landmarks | the same hands detected on the same sides in every clip; hand positions within 0.001–0.07 of the image width where both see a hand |
| Speed | ≈ 11 ms per frame for landmarker + model in the simulator on the Mac's CPU; says nothing about the iPhone |

So the landmarker swap (legacy → task) and the runtime swap (Python → iOS) don't change what the
model decides on these clips. Not shown: portrait phone footage, a live camera, device speed.

## Decision rule for the app (proposed, to be frozen on the phone session)

1. Full 250-way softmax. Never restrict to the vocabulary first.
2. Chip when top-1 ∈ vocabulary, p ≥ 0.6, margin over the runner-up ≥ 0.3, and the segment's
   tracking quality meets `data.QUALITY`.
3. "Pick one" tile when top-1 ∈ vocabulary and 0.35 ≤ p < 0.6: the candidate is shown, nothing
   is accepted until the user taps it or signs again.
4. Otherwise `?`. Non-vocabulary top-1 at any confidence is `?` (the other 240 classes are the
   "something else" bucket).
5. Per-word cut-offs are allowed (`tomorrow` at 0.45 is the obvious candidate) but only after a
   labelled session shows zero wrong accepts at that value.

## Vocabulary this supports (pure ASL)

| Status | Words | Evidence |
|---|---|---|
| Solid | hello, thankyou, yes, no, now, please, tomorrow | reference ≥ 0.7 and presenter ≥ 0.6 at least once (`tomorrow`: top-1 17/21, form fixable) |
| Candidates | morning, wait | presenter 0.62 once; reference 0.88 in a window |
| Dropped | sick, time | presenter and references flat or wrong |
| Also in the 250 and plausibly useful | yesterday, later, night, can, where, who, why, have, finish, callonphone, hungry, drink, water, home, go, see, hear, read | untested |

Script: hello → (purpose says doctor) → offered slot → no → tomorrow · please → yes → thankyou.

## Limitations

- One presenter, one laptop webcam, one free-form session with inferred labels: **not** the
  Gate 2 number. The labelled measurement is the phone clips (portrait front camera, scored on
  both paths with `spikes/recognition/asl_summary.py`); everything here predicts, nothing here proves.
- Lifeprint clips: one signer, 1–2 clips per word, standard YouTube licence, local only.
- INCLUDE/ISLRTC clips are landscape studio recordings; the presenter's October takes were
  recorded for a different experiment.
- The model's `hflip` training augmentation means left-handed signing should work; the presenter
  alternated hands and both were read, but this was not tested on purpose.
- No Deaf participant signed anything here. Isolated signs say nothing about conversation.

## Reproduce

```sh
cd spikes/recognition
# model (11 MB) and its own venv
mkdir -p artifacts/asl_signs && cd artifacts/asl_signs
curl -sL -o model.tflite https://huggingface.co/sign/kaggle-asl-signs-1st-place/resolve/main/model.tflite
curl -sL -o sign_to_prediction_index_map.json https://huggingface.co/sign/kaggle-asl-signs-1st-place/resolve/main/sign_to_prediction_index_map.json
python3 -m venv .venv && .venv/bin/pip install -q ai-edge-litert numpy && cd ../..
# clips: INCLUDE via range requests (gemini_probe/sources.py), ISLRTC mirror, Lifeprint via yt-dlp; see the manifests
.venv/bin/python ../asl_probe/extract.py --manifest artifacts/asl_probe/manifest.json
artifacts/asl_signs/.venv/bin/python ../asl_probe/infer.py --manifest artifacts/asl_probe/manifest.json --out artifacts/asl_probe/results.json
artifacts/asl_signs/.venv/bin/python ../asl_probe/infer.py --manifest artifacts/asl_probe/manifest_lifeprint.json --variants raw --window 2.0
.venv/bin/python ../asl_probe/live_probe.py --camera 0 --attempts 5          # guided webcam session
(cd artifacts/asl_signs && .venv/bin/python ../../../asl_probe/offline_analysis.py --session <id> --labels <labels.json>)
python3 ../asl_probe/teach.py && (cd artifacts && python3 -m http.server 8765)   # lesson page
# Run 4: app path in the simulator (H.264 clips in DIR), then the comparison
TEST_RUNNER_ISHARA_PARITY_CLIPS=DIR TEST_RUNNER_ISHARA_PARITY_OUT=OUT xcodebuild test \
  -project ../../ios/Ishara.xcodeproj -scheme Ishara -destination 'platform=iOS Simulator,name=iPhone 17' \
  -only-testing:IsharaTests/ASLParityHarness
.venv/bin/python ../asl_probe/parity.py --clips DIR --sim OUT --out parity.json
# per-word summary, gate and suggested thresholds for a labelled session
.venv/bin/python asl_summary.py --clips DIR      # or --records records.json, or --app OUT
```

Paid calls: none. Downloads: the model, 54 INCLUDE clips, 17 ISLRTC clips, 11 Lifeprint videos,
all under the gitignored artifacts directory.
