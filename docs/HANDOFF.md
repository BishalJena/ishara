# Teammate handoff

Snapshot: **20 October 2026**. Current implementation branch:
`spike/slgcn-miniature`. Start with this file, then use [PLAN.md](../PLAN.md) for
the active checklist. Older research and experiment notes retain their dated
conclusions; this snapshot and the active plan describe the latest state.

## The goal and today's status

We are building a hackathon communication aid for a Deaf or hard-of-hearing ISL
signer during a seated administrative appointment. The immediate job is to prove
the backend ML path before investing in the product interface.

**The diagnostic software runs. We have a promising recognition result for one
reused concept, not a validated five-sign recognizer or a complete calling app.**
No new model has been trained. There has been no Deaf participant validation.

The intended product flow is:

```text
One complete supported sign
  → compatible landmark extraction
  → recognition with an explicit unsure/reject outcome
  → concepts + purpose explicitly selected by the user
  → sentence preview and editing
  → one-time approval of the exact text
  → Bolna speech orchestration                       [unvalidated]
  → audio in the user's existing call                [unvalidated]
```

The current browser tool stops at local approval. SignCLIP matching is a separate
experiment; its uncalibrated ranks cannot feed composition or speech. The optional
LLM is also separate from the default fixed-template composer.

Meaningful **Bolna integration is mandatory**. The preferred target remains an
ordinary call started by the user from their own number. Do not route that call
through Bolna or create a second call. A service-originated or app-owned call is a
disclosed product pivot. System captions may be visible to the user; we have no
established app-readable transcript of the other person's Phone audio.

## What we have actually demonstrated

### Recognition

Three different experiments are easy to confuse:

1. **Original INCLUDE transformer, 263 classes:** 10/11 selected public dataset
   clips matched their labels after fixing always-on inference dropout. Seven
   saved intended-hello webcam segments produced no correct hello predictions.
   The model runs; the reason for the webcam failures is not established.
2. **OpenHands INCLUDE SL-GCN classifier, 263 classes:** 8/11 selected public
   clips and 0/7 intended-hello webcam segments matched. All seven webcam attempts
   abstained under the diagnostic candidate filter. This is the recognizer still
   used by the browser miniature.
3. **Frozen features with a five-concept reference bank:** SignCLIP ranked hello
   first for 7/7 saved intended-hello attempts; SL-GCN features ranked hello first
   for 0/7. Both used the same eight public references. On six public queries that
   had another same-label reference, SignCLIP scored 5/6 and SL-GCN features 6/6.
   Queries cannot match their own ID, content hash or source ID. Doctor and tomorrow
   each have a singleton reference, so their public clips cannot score themselves.

The first two classify across 263 labels; the third retrieves among five concepts.
Their scores are not interchangeable benchmarks. The seven webcam segments are
all intended to mean hello, from two old sessions, without independent linguistic
verification. They do not establish accuracy for the other four target signs.

**Current choice:** take SignCLIP into the fresh-data pilot, keeping SL-GCN as the
comparison. The pilot vocabulary is `hello`, `thankyou`, `doctor`, `hospital`,
`tomorrow`. The older browser diagnostic also supports `today` and `location`.

**Why it is still blocked from speech:** an out-of-scope today clip matched hello
at 0.931 cosine similarity, higher than all seven intended-hello matches
(0.532–0.590). A similarity is not calibrated confidence. Every retrieval replay
returns abstention; supported attempts and real negatives must calibrate rejection.

**Timing:** SignCLIP embedding inference had a median of about 54 ms on CPU.
Original whole-clip landmark extraction had a median of 1.59 s for public clips
and 2.93 s for the webcam clips, which contain 47–169 frames. SL-GCN feature
inference was about 20 ms, with extraction medians of 3.72 s and 7.08 s respectively.
These are batch measurements, not sign-completion-to-visible-result latency.
The two-second live target has not passed.

### Sentences and approval

The initial local Qwen experiment generated a useful appointment request but also
changed “today,” with requested-day intent, into a question about the day. An LLM
cannot safely infer missing intent or repair an incorrect recognized concept.

The default is now deterministic:

- `doctor + tomorrow` with request-appointment intent → “I would like an
  appointment with a doctor tomorrow.”
- `today` with specify-day intent → “I would like today.”
- Missing purpose, incompatible concepts or conflicting days → no approvable draft.

The user can edit the exact sentence. Approval is single-use and invalidated by
new analysis, a new draft or reset. Supplied concepts are labeled as bypassing
recognition. Approval explicitly reports that speech is not connected.

The real public doctor/tomorrow clips → SL-GCN predictions → fixed sentence →
edited approval path passed in Helium. **34 backend/data tests and 20 browser
checks passed.** Test success establishes those software boundaries, not model
accuracy on new signers.

Before publishing, the tracked files were also exported to a clean directory with
no credentials, downloaded assets or private recordings. The same test commands
passed there, with the one OpenHands transform test skipped because its source
checkout was absent. This reused the installed Python environment; it was not a
fresh dependency installation or a repeated model benchmark.

### Bolna and the iPhone harness

The separate [call-flow spike](../spikes/call_flow/README.md) contains:

- An offline lifecycle simulation and **13 passing tests**. Its signs, audio
  completion and captions are synthetic; Phone/WhatsApp are scenario labels.
- A non-telephony Bolna probe. Earlier account/catalog GETs returned 200; a
  historical speech-sample request returned 403 and produced no audio. It did
  not establish speech access or measure speech latency.
- An Apple AAC sample adapted for fixed speech, Stop, external audio playback
  and a front-camera preview. Earlier unsigned and signed development builds
  passed. No physical call/caption/camera coexistence test was completed.

Bolna OSS text/audio orchestration remains a researched integration path. No
working Bolna-to-existing-Phone-call chain has been demonstrated. An Apple local
voice test alone would not satisfy the mandatory Bolna integration.

## Get the code and run it

These commands target the tested Mac/POSIX setup. ML experiments used Python 3.11
on Apple Silicon. Other OS/device compatibility has not been verified. Install
Git and `uv` first; the environments and model assets require several GB.

```sh
git clone --branch spike/slgcn-miniature git@github.com:BishalJena/ishara.git
cd ishara
```

For an existing checkout, first preserve any local work, then fetch and switch
to that branch. Repository access is required because the repository is private.

### Quick offline orientation

No model downloads, provider credentials or network requests are needed:

```sh
python3 spikes/call_flow/flow_mock.py
python3 -m unittest discover -s spikes/call_flow -p 'test_*.py'
```

### Browser miniature and public clip replay

```sh
uv venv --python 3.11 spikes/recognition/.venv
uv pip install --python spikes/recognition/.venv/bin/python \
  -r spikes/recognition/requirements.txt
cd spikes/recognition
.venv/bin/python setup_mini.py
.venv/bin/python fetch_clips.py
.venv/bin/python -m unittest -v test_mini test_retrieval
.venv/bin/python mini.py evaluate
.venv/bin/python mini.py serve
```

Open **http://127.0.0.1:8088**. Inspect a public doctor clip and a tomorrow clip,
choose the appointment-request purpose, compose, edit and approve. Try the
supplied-concept day/conflict examples separately.

`setup_mini.py` downloads the pinned OpenHands source/checkpoint/metadata and the
optional Qwen assets (about 1 GB), even though templates are the default.
`--composer llm` enables the earlier LLM experiment. `mini.py evaluate` writes
local evidence and can run with only public clips.

**A clean checkout has no private webcam recordings.** Its replay denominator
will therefore differ. Public downloads can also be unavailable or incomplete;
inspect the fetched inventory rather than assuming a count. Do not invent missing
clips or present the seven-clip result as reproduced on your machine.

The existing UI is a loopback diagnostic, not a deployed service. For a local
preview proxy, pass its exact address with `--preview-origin`; do not disable
browser security. [Detailed commands and input contracts](../spikes/recognition/README.md)
include the older INCLUDE harness, capture controls and the browser test script.

### SignCLIP comparison

From `spikes/recognition`, after setting up the public corpus above:

```sh
mkdir -p artifacts/signclip
uv venv --python 3.11 artifacts/signclip/.venv
uv pip install --python artifacts/signclip/.venv/bin/python \
  -r requirements-signclip.txt
artifacts/signclip/.venv/bin/python setup_signclip.py
artifacts/signclip/.venv/bin/python retrieval.py replay --encoder signclip
.venv/bin/python retrieval.py replay --encoder slgcn
.venv/bin/python retrieval.py status
```

Keep these environments separate: they pin different Transformers versions.
SignCLIP setup downloads the official multilingual checkpoint (~2.4 GB), pinned
upstream source and BERT tokenizer/configuration metadata. Runtime inference is
local. Model hashes, compatibility adjustments and observed dependency freezes
are documented in the spike README. `status` is expected to report missing fresh
pilot data on a clean checkout.

## Where the work lives

- `spikes/recognition/`: original INCLUDE harness; SL-GCN browser miniature;
  SignCLIP adapter; capture/review; retrieval, calibration and evaluation; tests.
- `spikes/call_flow/`: offline flow mock, real provider probe and licensed iOS
  diagnostic source. Provider commands make real requests and are not part of
  the offline tests.
- `PLAN.md`: active ML execution, pilot criteria and historical checkpoints.
- `docs/RESEARCH.md`: research navigation and corrections.
- `docs/CLAIM-LEDGER.md`: source claims, executed observations and unresolved gates.
- `docs/WORKFLOW.md` and `docs/VALIDATION-PLAN.md`: proposed product behavior and
  broader validation requirements.
- `research-links.md`: original research leads, not blanket endorsements.

The published tree deliberately excludes `.env`, private recordings, model
weights, caches, generated evidence/audio, account responses, signing identities
and editor-local canvases. Measured aggregate results are recorded here and in
the spike README. Public assets can be fetched using the scripts. Locally generated
reports live in `spikes/recognition/artifacts/{mini,retrieval}/`; those files are
not available merely by cloning this branch.

## Research decisions worth reading

1. [ISL recognition landscape](<reports/ISL recognition landscape.md>) and
   [source audit](<research_notes/ISL recognition source audit.md>): models,
   released weights, input contracts, datasets, evaluation splits and licenses.
   Many listings recognize alphabets or tiny vocabularies; paper accuracy does
   not establish transfer to our camera and signer.
2. [ASL transfer review](<reports/ASL transfer for Ishara.md>): CISLR supports the
   method of ASL-pretrained features plus labeled ISL references. SignCLIP's
   multilingual inventory includes ISL. This motivated reference matching before
   collecting a large training dataset. ASL output labels cannot simply be renamed.
3. [Independent Ishaara AI audit](<reports/Ishaara AI source audit.md>): their
   six-class GRU and current eighteen-label image detector are different systems.
   They offer useful data-collection and bounded-model patterns, but no demonstrated
   appointment vocabulary or independent-signer reliability. Their code/weights
   were inspected, not adopted; no explicit repository license was found.
4. [Proposed flow and Eraser sources](<reports/Ishara proposed flow.md>): editable
   diagram source is committed here. The external Eraser file has link access
   disabled and may require team access; the repository text remains usable.
5. [Product directions](<reports/Ishara hackathon product directions.md>) and
   [Bolna paths](<research_notes/Ishara hackathon product directions/bolna-paths.md>):
   why native calling is preferred, what meaningful Bolna integration could do,
   and which alternatives would change the product.

These reviews are dated snapshots. Some predate the local SignCLIP execution;
their “not yet run” statements do not override this handoff's measured update.
Code, dataset and checkpoint licenses are distinct. We include the MIT notice
for adapted INCLUDE code and Apple's sample license; public model availability
does not establish unrestricted redistribution rights.

## Next work and decision gates

**Recognition track:** first capture 3 complete takes per concept in one seated
session (15 total), then review tracking and sign forms with appropriate ISL
expertise/reference material. Use one session ID throughout that session:

```sh
# From spikes/recognition; repeat for the other four target concepts.
.venv/bin/python pilot_capture.py capture \
  --signer demo --session enrollment-01 --split enrollment \
  --concept hello --takes 3 --camera 0
```

SPACE starts/stops; X discards; Q exits. Takes start unverified. The README explains
`review` and `verify`; a landmark overlay alone does not verify a sign's meaning.
File encoding and overlay rendering have been tested; actual keyboard-driven
camera collection still awaits the first new session.

Then collect a different calibration session: at least 5 examples per concept
and 20 negative clips spanning idle, transitions, incomplete and unsupported signs.
Choose the encoder and freeze its thresholds using this development data.
Calibration cannot pass by rejecting everything.

The separate final test needs at least 10 attempts per concept and 50 negatives.
Require at least 90% correct accepts per concept, no wrong accepted supported
labels and no negative accepts. If test failures inform changes, retire that test
as development evidence and collect a new final session. Evaluate fresh extraction;
batch timing does not prove the separate two-second visible-response target.

Do not start training solely to improve the seven reused hello clips. If reference
matching cannot separate the target signs, diagnose tracking/sign variation and
use that evidence to choose limited adaptation and additional development data.

**Speech/device track, independently:** prove exact approved synthetic text →
genuine Bolna audio → controllable playback/cancellation. Then test delivery into
an existing, user-started call with a consenting recipient, followed by simultaneous
camera and captions. Calls, paid inference and deployment need task authorization.

Only after those gates should we connect calibrated recognition to speech and
build polished demo UX. A passing personalized isolated-sign pilot still would
not establish general ISL translation, natural conversation or accessibility
validation with Deaf participants.
