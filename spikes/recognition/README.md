# Recognition runbook

Local diagnostics, not a deployed recognition service.
[Handoff](../../docs/HANDOFF.md) · [Measured results](../../docs/experiments/recognition.md) ·
[Active gates](../../PLAN.md) · [Historical notebook](../../docs/archive/2026-10-20-recognition-notes.md)

Commands below run from `spikes/recognition` on the tested Mac/Python 3.11 setup.
Git and `uv` are prerequisites. Weights, videos, caches and generated evidence
stay under ignored `artifacts/`; no credentials are needed for the public models.

## Set up the browser miniature

```sh
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python setup_mini.py
.venv/bin/python fetch_clips.py
.venv/bin/python -m unittest -v test_mini test_retrieval
.venv/bin/python mini.py evaluate
.venv/bin/python mini.py serve
```

Open **http://127.0.0.1:8088**. Analyze public doctor and tomorrow clips, select
appointment-request purpose, compose, edit and approve. Approval records text
locally; speech is not connected. Supplied-concept mode is explicitly separate
from recognition.

Setup fetches OpenHands source/checkpoint/metadata and the optional Qwen assets
(about 1 GB). Default composition uses fixed templates; `--composer llm` selects
the historical LLM experiment. Evaluation writes `artifacts/mini/evaluation-templates.json`;
LLM evaluation uses `evaluation.json`.

Personal webcam clips are not distributed. Inspect download warnings and inventory:
missing public/private clips change replay denominators. The backend is a
single-user, single-turn diagnostic bound to loopback; reset between utterances.
It currently uses SL-GCN, while uncalibrated SignCLIP ranks stay in the separate tool.

For a preview proxy, allow its exact current origin:

```sh
.venv/bin/python mini.py serve --preview-origin http://127.0.0.1:64343
```

Replace that example port with the preview's actual port. Unrelated origins stay
blocked. The browser regression is `test_mini_browser.js`, runnable through
Playwright MCP's `browser_run_code_unsafe` filename argument with the local tab
selected. It exercises real public clips, resets the turn and expects two
deliberate HTTP 400 responses.

## Set up SignCLIP separately

Do not install its requirements into `.venv`: Transformers versions differ.

```sh
mkdir -p artifacts/signclip
uv venv --python 3.11 artifacts/signclip/.venv
uv pip install --python artifacts/signclip/.venv/bin/python -r requirements-signclip.txt
artifacts/signclip/.venv/bin/python setup_signclip.py
artifacts/signclip/.venv/bin/python retrieval.py replay --encoder signclip
.venv/bin/python retrieval.py replay --encoder slgcn
```

Setup fetches the pinned upstream source, ~2.4 GB multilingual checkpoint and BERT
tokenizer/config metadata; it does not fetch BERT base weights. Inference is local.
Replay compares the same saved corpus and always abstains until a fresh pilot
supports calibration. Similarities are not confidence probabilities.

SignCLIP extracts body, hands and face contours with pose-format 0.9.0 / Holistic
0.10.21 complexity 1 and upstream normalization, producing 609 values per frame.
SL-GCN has its own 27-joint input and preprocessing. Preserve raw video; their
landmark caches are not interchangeable. SignCLIP rejects more than 256 frames
rather than silently truncating. Neither path invents a missing sign.

## Sign Lab quick try (before calibration)

Record 3 takes of each of the 12 signs in about 10 minutes, then try live recognition
straight away. This is **not** the R3 calibration session or Gate 2: the cut-offs are
provisional and nothing here counts as measured accuracy.

```sh
.venv/bin/python record_session.py --camera 0                     # guided enrollment
artifacts/signclip/.venv/bin/python retrieval.py export-bundle --encoder signclip --provisional
../../scripts/sign_lab.sh                                         # the Sign Lab (repo root: scripts/sign_lab.sh)
```

**Camera permission (macOS):** the first run asks to let your terminal app (Terminal,
iTerm, VS Code...) use the camera. If it says it can't open the camera or the window
stays black, turn the app on in System Settings → Privacy & Security → Camera, then
quit and reopen the terminal.

**Before you start:** sit so your face, shoulders and both hands are in the frame.
Between signs rest both hands on the table. After each sign drop your hands and hold
still for about half a second; that's how the take ends.

Each take:

```
 hands resting ─ SPACE ─▶ 3-2-1 countdown ─▶ GO: sign once ─▶ hands down, still ~0.5 s
                          (rest line measured)                     │ take ends by itself
                                                                   ▼
                     K keep ◀── replay with the tracking overlay ──┘ ──▶ R redo
```

- The window shows the sign, a one-line hint and where to watch the reference
  (INCLUDE for most signs, the ISLRTC dictionary for yes, no and sorry). The terminal
  prints the full link and any local INCLUDE copy under `artifacts/clips/`. Videos are
  only linked, never downloaded or shared by this tool.
- The take keeps exactly the detector's cut (0.2 s before the hands rise to the first
  frame back at rest), the same frames the live recognizer matches.
- If something goes wrong it says why and waits for SPACE: shoulders not visible,
  hands moved during the countdown, too short or too long (over 4 s), no sign within
  8 s. **X** discards a take, **Q**/escape stops the session.
- **K** only when the replay matches the reference: the take is saved as a verified
  enrollment clip with the note "self-checked during guided Sign Lab session against
  &lt;reference&gt;". Takes go to the same `artifacts/pilot/dataset.json` and
  `artifacts/pilot/clips/` as `pilot_capture.py`, split `enrollment`, signer `demo`, one
  session `signlab-YYYYMMDD`.
- **Resume:** run it again with the session ID it printed (`--session signlab-20261024`);
  signs that already have enough kept takes are skipped. `--takes N` changes the count,
  `--manual-stop` uses SPACE to stop instead of the detector (whole take kept).

`export-bundle --provisional` uses the verified enrollment takes only (it refuses while
any enrollment take is unverified) and needs at least 2 takes of every sign. It writes
`artifacts/evidence/recognition-bundle-signclip-provisional.json`, never the calibrated
`recognition-bundle-signclip.json`, and no policy file. The schema is the normal bundle's
plus `"provisional": true` and `leave_one_out` counts, and it prints a
**PROVISIONAL — uncalibrated, for trying only, not Gate 2** banner.

How the cut-offs are picked (leave-one-out): each take is ranked against all the other
takes, never itself. Cut-offs sit at observed correct matches; the one accepting the most
takes with **0 wrong accepts** wins (the lowest on ties). A cut-off that accepts nothing is
never chosen: if every useful one has a wrong accept, it falls back to similarity 0.90 and
margin 0.05 and the banner says FALLBACK. Deviations from R2b, on purpose: queries and
references come from the same session minutes apart, and there are no negatives, so the
counts are optimistic and idle or unsupported movement was never measured. `evaluate` and
the calibrated `export-bundle` refuse provisional cut-offs, and the iOS bundle loader
refuses provisional bundles. The enrollment takes still count for R1; R3 is still needed.

## Capture and review

Begin with the enrollment budget in [PLAN.md](../../PLAN.md). Keep one pseudonym
and one session ID throughout a recording session, including across commands:

```sh
.venv/bin/python pilot_capture.py capture \
  --signer demo --session enrollment-01 --split enrollment \
  --concept hello --takes 3 --camera 0
```

Repeat for each of the 12 demo signs (`--concept` accepts exactly these):
hello, thankyou, yes, no, sorry, doctor, today, tomorrow, morning, afternoon,
evening, time. **SPACE** starts/stops a take;
**X** discards; **Q/escape** exits and discards an unfinished take. Keep face,
shoulders and hands visible, with a complete sign and brief neutral boundaries.
Long takes are rejected, not cropped. The camera requests 1280×720 at 30 FPS;
actual dimensions, timestamps and frame gaps are retained, with encoding at the
measured mean FPS. Camera permission may be required for the terminal app.

Every take is unverified. Raw clips and the manifest stay under `artifacts/pilot/`.
Use the printed clip ID to review tracking and check the sign against appropriate
ISL expertise/reference material:

```sh
.venv/bin/python pilot_capture.py review --id CLIP_ID
.venv/bin/python pilot_capture.py verify --id CLIP_ID \
  --note "Describe the actual sign-form review and the ISL reference used"
```

`review --headless` writes the full overlay without opening a window. Reviews
never show predictions. `verify` records your explicit label assertion and note;
tracking quality does not automatically verify ISL meaning.

For later negative collection use `--concept idle`, `transition`, `incomplete` or
`unsupported`, with an explanatory `--note` and the correct calibration/test split.
Enrollment accepts supported concepts only.

## Calibrate and evaluate

```sh
.venv/bin/python retrieval.py status
artifacts/signclip/.venv/bin/python retrieval.py calibrate --encoder signclip
.venv/bin/python retrieval.py calibrate --encoder slgcn
# Select the encoder on development evidence before inspecting the final test.
artifacts/signclip/.venv/bin/python retrieval.py evaluate --encoder signclip --fresh
```

The [active plan](../../PLAN.md) owns coverage and pass criteria. Manifests reject
duplicate videos and session/source/hash overlap across splits. Frozen policies
are bound to encoder and development fingerprints. Missing data, unverified labels,
nonfinite evidence and reject-all calibration cannot pass.

`calibrate` uses the calibration session only. It needs attempts for all 12 signs
and at least 20 negatives, then picks the cut-off (similarity plus margin over the
runner-up) that keeps the most correct accepts with **at least 60% per sign, 0 wrong
accepts and 0 negative accepts** (PLAN R2b). If no cut-off qualifies it fails rather
than freezing one that rejects everything. Besides `artifacts/retrieval/policy-<encoder>.json`
it writes and prints `artifacts/evidence/calibration-<encoder>.md`: cut-off, margin,
accepted/attempts per sign, wrong accepts and negative accepts with denominators.

## Export the iPhone bundle

```sh
artifacts/signclip/.venv/bin/python retrieval.py export-bundle --encoder signclip
```

Writes `artifacts/evidence/recognition-bundle-<encoder>.json` for the on-device
matcher (P2):

```json
{"version": 1, "encoder": "<encoder contract as canonical JSON>", "embedding_dim": 768,
 "thresholds": {"similarity": 0.0, "margin": 0.0},
 "quality": {"min_pose_fraction": 0.6, "min_hand_fraction": 0.2},
 "references": [{"id": "<clip id>", "label": "hello", "embedding": [0.0]}]}
```

It refuses when the enrollment/calibration data changed since `calibrate`, or the
loaded encoder contract differs from the frozen policy; re-run `calibrate` first.
The quality values come from `recognition_data.QUALITY`, the same constant the Mac
decision uses. References are Mac-extracted embeddings of the enrollment clips;
the parity task (P3) re-embeds them with the iOS extractor before the iPhone relies
on them. The bundle contains personal enrollment embeddings, so it stays under
ignored `artifacts/`.

`--fresh` disables feature caching. Reported batch timing still excludes capture,
ranking and display; `live_latency_validated` and `demo_ready` stay false.
If final-test findings drive changes, collect a new final test session.

## Mac fallback: live recognizer into the call (PLAN A4)

The demo safety net when the on-device recognizer isn't ready: the Mac webcam
recognizes signs and the bridge posts them as chips to the same backend call
WebSocket the app uses. Nothing is spoken until you press `s` (SEND).

```
 terminal (bridge venv: websockets only)              child process (SignCLIP venv: torch, MediaPipe)
 mac_bridge.py --live ──starts──▶ live_source.py ── webcam / --replay-videos clips
      ▲                                │  legacy Holistic once per frame
      │  one JSON line per sign        │  → detector (2 s rest calibration, rest line)
      └──── stdout ◀───────────────────┘  → accepted segment → SignCLIP features + embedding
      │                                   → bundle: rank + decision, frozen thresholds
      ▼                                   → sign, or null (unsure "?")
 backend WebSocket: chips / approve / stop / end      logs, rest line, latency → stderr (terminal)
```

The two venvs stay separate: the bridge venv can't import torch, and the SignCLIP
venv pins its own Transformers. The bridge starts the recognizer as a child process
with the SignCLIP venv's Python (`--recognizer-python`, default
`artifacts/signclip/.venv/bin/python`). Only result lines go to its stdout; any
other printing, including native MediaPipe/torch output, goes to stderr.

### One-time setup

The light `.venv` and the SignCLIP venv as above, plus the bridge venv:

```sh
uv venv --python 3.11 artifacts/bridge/.venv
uv pip install --python artifacts/bridge/.venv/bin/python --require-hashes -r requirements-bridge.lock
artifacts/bridge/.venv/bin/python -m unittest test_mac_bridge test_detector test_detect_clips
.venv/bin/python -m unittest test_live_source test_record_session   # fakes only: no webcam, no model
```

### Runbook

1. **Enrollment (R1).** Same signer who presents the demo. 3–5 takes per sign in
   one session, then `review` and `verify` each clip
   ([Capture and review](#capture-and-review)), or the guided
   [Sign Lab session](#sign-lab-quick-try-before-calibration) (`record_session.py --takes 5`):

   ```sh
   .venv/bin/python pilot_capture.py capture --signer demo --session enrollment-01 \
     --split enrollment --concept hello --takes 5 --camera 0
   ```

2. **Calibration (R3).** A new session: 5 takes per sign plus at least 20 negatives
   covering idle, transition, incomplete and unsupported. Verify every clip.

   ```sh
   .venv/bin/python pilot_capture.py capture --signer demo --session calibration-01 \
     --split calibration --concept hello --takes 5 --camera 0
   .venv/bin/python pilot_capture.py capture --signer demo --session calibration-01 \
     --split calibration --concept idle --takes 5 --camera 0 --note "hands resting, no sign"
   .venv/bin/python retrieval.py status
   ```

3. **Freeze the cut-off (R2b).** Read the printed report: every sign at least 60%,
   0 wrong accepts, 0 negative accepts.

   ```sh
   artifacts/signclip/.venv/bin/python retrieval.py calibrate --encoder signclip
   ```

4. **Export the bundle.**

   ```sh
   artifacts/signclip/.venv/bin/python retrieval.py export-bundle --encoder signclip
   ```

5. **Check it alone, no call.** Rest both hands for 2 s when asked (it prints
   `rest line y=...`), then sign one at a time and drop your hands after each.
   Every accepted segment prints the sign or `? (reason)` and its latency.
   **q** in the window or Ctrl-C stops and prints the latency summary.

   ```sh
   artifacts/signclip/.venv/bin/python live_source.py --camera 0
   # rehearse with saved clips through exactly the same path (paced like a camera):
   artifacts/signclip/.venv/bin/python live_source.py --replay-videos artifacts/rehearsal
   ```

   `--replay-videos DIR` plays every .mp4/.mov/.m4v in DIR in name order. Each clip
   calibrates on its first 2 s; for takes without a leading rest, pass the
   `--rest-y` that live mode printed in the same seat. `--fast` skips the pacing,
   but then latency no longer means live latency.

6. **Into the call.** Attaching to a call the app or backend already started costs
   nothing. Starting one needs `--contact clinic --confirm-cost` (it dials a real,
   allowlisted phone and costs money; see the bridge's cost heads-up).

   ```sh
   export APP_TOKEN=...   # from the team secret store; never commit it
   artifacts/bridge/.venv/bin/python mac_bridge.py --base-url https://<backend> \
     --call-id <call_id> --live --camera 0
   # rehearsal: recorded clips instead of the webcam
   artifacts/bridge/.venv/bin/python mac_bridge.py --base-url https://<backend> \
     --call-id <call_id> --live --replay-videos artifacts/rehearsal
   ```

   Signs become chips, `?` stays local, drafts arrive from the backend and you
   press `s` to SEND. You can still type signs, `x`, `c`, `q yes|no|wait|repeat`,
   `stop` and `e` (`h` lists them). If the recognizer stops, the bridge says so
   and typed signs still work. `--bundle PATH` and `--rest-y Y` are passed to
   the recognizer.

### What the recognizer guarantees

- Each sign uses the same `recognition_data.rank` and `decision` as calibration,
  with the bundle's frozen thresholds and the shared quality minimums.
- Rejected segments (too short, too long, lost tracking) and clips that end
  mid-sign yield nothing.
- An accepted segment yields `?` when the match is weak, the runner-up is too close,
  tracking is poor, the shoulders can't be found, or it has more than 256 frames
  (SignCLIP's limit; never truncated).
- Without a bundle it warns at start and every sign is `?`. A bundle from another
  SignCLIP setup (checkpoint, source, torch version or threads) stops it at start:
  re-run `export-bundle` in the same venv.
- Latency runs from the moment your hands are back at rest to the result. That
  includes the detector's 0.4 s rest wait. G2 wants under 2 s live, so take the
  number from `--camera`, not `--fast`.
- Holistic runs once per frame. The SignCLIP features come from those same
  landmarks, and on a public clip they matched `signclip.extract` exactly.

**Known gap:** the bundle references and the calibration cut-off come from whole
takes, while live matching sees only the detector's cut (0.2 s before the hands
rise to the first rest frame). On one public clip, the cut's embedding had a cosine
of 0.86 with the whole-clip embedding. Before trusting the frozen cut-off live,
replay the calibration takes with `live_source.py --replay-videos` and check that
they come out as calibrated.

## Historical INCLUDE harness

Retained for comparison; it is not the active fresh-data candidate.

```sh
git clone https://github.com/AI4Bharat/INCLUDE.git artifacts/INCLUDE
git -C artifacts/INCLUDE checkout df348f4a640060d4d39f02556d9f96851e8c46c7
.venv/bin/python eval_clips.py
.venv/bin/python live.py --list-cameras
.venv/bin/python live.py --camera 0 --reference hello
```

Reuse an existing pinned clone rather than cloning over it. First model load
downloads the checkpoint. `live.py --help` documents replay/scoring controls.
The segmentation/framing guide approximates sampled dataset conditions; it does
not establish a standing-distance requirement or reliable seated recognition.
The adapted code retains the [upstream MIT notice](INCLUDE-LICENSE.txt).

## Reproducibility notes

Requirements pin the compatible MediaPipe/OpenCV/Transformers versions; observed
freezes are local snapshots. The legacy MediaPipe wheel has a platform-tag warning,
although the inspected native extension contains arm64 and x86_64 slices and the
recorded extraction ran on arm64. Do not claim a clean cross-platform install.

Hashes and executed compatibility checks are in the
[experiment record](../../docs/experiments/recognition.md); source revisions and
input contracts are also explicit in each adapter. OpenHands is Apache-2.0 and
its license stays in the downloaded clone. INCLUDE videos have CC-BY-4.0 terms.
Consult the [source audit](../../docs/research/recognition/source-audit.md) for
separate code, checkpoint and dataset licensing considerations.
