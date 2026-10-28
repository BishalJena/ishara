# Recognition runbook

Local diagnostics, not a deployed recognition service.
[Handoff](../../docs/HANDOFF.md) · [Measured results](../../docs/experiments/recognition.md) ·
[Active gates](../../PLAN.md) · [Historical notebook](../../docs/archive/2026-10-20-recognition-notes.md)

> **Current path (decision D8, 25 Oct): the public ASL Signs model, used as is.** It runs
> behind the same detector with `--model asl` (`live_source.py`, `mac_bridge.py`,
> `scripts/sign_lab.sh`); the rule is in `asl_matcher.py`, its bundle in `fixtures/asl/`, and
> `asl_summary.py` scores a labelled session. Setup and results:
> [ASL model probe](../../docs/experiments/asl-model-probe.md), tools in
> [`../asl_probe`](../asl_probe/README.md). Most of this runbook covers the earlier ISL work
> (the browser miniature, SL-GCN, personalised SignCLIP references), kept because SignCLIP is
> still the app's fallback and the measurements depend on it.

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

`.venv/bin/python -m unittest light_tests` runs every `test_*.py` here and in
`../asl_probe` except the exclusions `light_tests.py` names (`test_mini`, the clip-driven
fallback); `scripts/verify.sh` and CI run the same list, so a new test file needs no edit there.

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

The recognizer starts **before** the call. The bridge runs it with `--handshake`:
once it has loaded and calibrated, it prints one ready line and holds. Only then does
the bridge create the brief, place (or join) the call and connect. Once connected, it
writes `go` to the recognizer's stdin and signs start to count. Saved clips pause while
holding. A camera keeps running, but nothing it sees before `go` becomes a chip. If the
recognizer stops before it is ready, nothing is dialled and the bridge exits with
`! the live recognizer stopped before it was ready (exit N); no call was placed`.

```
 mac_bridge --live            live_source --handshake           backend
   │ start ─────────────────────▶ load model, 2 s rest
   │ ◀── {"event": "ready"} ───── calibrated, holding
   │ POST /briefs, /calls, WebSocket ──────────────────────────▶ call starts
   │ go ────────────────────────▶ recognising
   │ ◀── one line per sign ─────
```

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

5. **Check it alone, no call (Sign Lab).** Rest both hands for 2 s when asked (it
   prints `rest line y=...`), then sign one at a time and drop your hands after each.
   **q** in the window or Ctrl-C stops and prints the latency summary.

   Every accepted segment prints one line with the top 3 matches, the margin to the
   runner-up and the latency; a `?` also says which cut-off it missed:

   ```
   #2 0.76-1.60 s  ✓ doctor  (doctor 0.77 | today 0.62 | hello 0.62; margin 0.15; 0.47 s)
   #3 0.60-1.36 s  ? unsure  (today 0.88 | tomorrow 0.86 | hello 0.79; margin 0.02; 0.71 s; low margin)
   ```

   The window shows the same for the latest sign until it is replaced:

   ```
   ┌──────────┐                                     ┌───────────────────────────────┐
   │ watching │ ← detector pill                     │ doctor   ← green, or a red ?  │
   └──────────┘   (calibrating/signing/cant see)    │            with why under it  │
   ██ PROVISIONAL - uncalibrated, for trying only ██│ doctor  ██████████│█  0.77    │
      ↑ red banner, only for a provisional bundle   │ today   ███████   │   0.62    │
                                                    │ hello   ███████   │   0.62    │
                                                    │ margin 0.15 (min 0.05)  0.47 s│
                                                    │ body 1.00 (min 0.60) hands ...│
   rest line ─────────────────────────────────────  └───────────────────────────────┘
   #2 doctor  0.47 s                                  │ = the similarity cut-off
   ```

   Bars run from 0 to 1. `low similarity` means even the best match is below the
   cut-off; `low margin` means the runner-up is too close; `body/hands seen in too
   few frames` means tracking was poor. A bundle marked `"provisional": true` is
   accepted for trying signs out, but every line says `[PROVISIONAL]` and the
   window shows a red banner: its thresholds are not calibrated, so nothing it
   says counts as a G2 measurement.

   ```sh
   artifacts/signclip/.venv/bin/python live_source.py --camera 0
   # rehearse with saved clips through exactly the same path (paced like a camera):
   artifacts/signclip/.venv/bin/python live_source.py --replay-videos artifacts/rehearsal
   ```

   `--replay-videos DIR` plays every .mp4/.mov/.m4v in DIR in name order. Each clip
   calibrates on its first 2 s; for takes without a leading rest, pass the
   `--rest-y` that live mode printed in the same seat. `--fast` skips the pacing,
   but then latency no longer means live latency. Replayed clips get the same
   window; `--no-preview` turns it off. Short public clips have no 2 s rest of their
   own; play them as one camera with `--video` instead ([Demo fallback](#demo-fallback-asl-model-rehearsed-from-clips)).

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

   Rest both hands for 2 s first: the bridge joins or places the call only once the
   recognizer prints `live recognizer ready`. Signs become chips, `?` stays local, drafts arrive from the backend and you
   press `s` to SEND. You can still type signs, `x`, `c`, `q yes|no|wait|repeat`,
   `stop` and `e` (`h` lists them). If the recognizer stops, the bridge says so
   and typed signs still work. `--bundle PATH` and `--rest-y Y` are passed to
   the recognizer.

   Each sign prints the same per-sign line as step 5. Backend events (status,
   receptionist captions, the voice's own lines as `Ishara (voice): …`
   (disclosure, holding line, goodbye), drafts with their `llm`/`template`
   source, SEND and `Delivered`) carry a time. `--log` also appends every recognizer result and
   every message sent or received to a JSONL file for review afterwards, by default
   `artifacts/lab/session-<date>-<time>.jsonl` (`--log PATH` must stay inside the
   gitignored `artifacts/`):

   ```sh
   jq -c 'select(.from == "recognizer") | .message | [.sign, .top[0].sign, .margin]' \
     artifacts/lab/session-*.jsonl
   ```

### What the recognizer guarantees

- Each sign uses the same `recognition_data.rank` and `decision` as calibration,
  with the bundle's frozen thresholds and the shared quality minimums.
- Only `sign` in a result line becomes a chip. `top`, `quality`, `thresholds`,
  `failed_checks` and `provisional` are for display and the session log; the old
  keys (`reason`, `latency_ms`, `similarity`, `margin`, `segment`) are unchanged.
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

## Demo fallback (ASL model, rehearsed from clips)

The safety net for demo day: if the phone's recognizer fails, the Mac recognizes the
signs with the public ASL model (`--model asl`, decision D8) and the bridge posts the
chips to the same backend call. It works in live mode (you press `s` to SEND) and in
Call for me (`--delegated --attended`), where you answer the agent's question by
signing yes / no / wait or typing `a yes|no|wait`.

```
 saved clips (--video) ─┐
                        ├─▶ live_source.py --model asl ──▶ mac_bridge.py ──WebSocket──▶ backend call
 webcam (--camera 0) ───┘    2 s rest calibration once,      chips, SEND,        (local or deployed)
                             detector, ASL model,            answers
                             open-set rule
```

`--video A B C` plays the clips one after the other as if they were the webcam: one
clock, real-time pace, one rest calibration at the start, then the same detector.
Start with a hands-down rest clip and put a rest clip between turns. (`--replay-videos`
calibrates every clip on its own first 2 s, so short per-word clips give nothing.)

### Setup (once)

- The recognition `.venv` ([Set up](#set-up-the-browser-miniature)) and the bridge venv
  ([One-time setup](#one-time-setup)).
- The ASL model and its venv in `artifacts/asl_signs/`: *Reproduce* in
  [asl-model-probe.md](../../docs/experiments/asl-model-probe.md).
- For rehearsals and the automated check, Lifeprint (ASL University, Bill Vicars) clips in
  `artifacts/fallback_clips/` (gitignored, standard YouTube licence: local use only, never
  commit or upload them). The rest clip is 2.0 s of the signer with both hands out of frame:

  ```sh
  # from spikes/recognition; needs yt-dlp (uv tool install yt-dlp) and ffmpeg (brew install ffmpeg)
  mkdir -p artifacts/fallback_clips && cd artifacts/fallback_clips
  for pair in rest:4gAd3p_Jgq8 hello:FVjpLa8GqeM thankyou:2W0BDFUjsG0 yes:0usayvOXzHo \
              no:QJXKaOSyl4o please:rnb9FxPO7is tomorrow:6gFOZMDptIk morning:iH8N44QMh7c; do
    name=${pair%%:*} id=${pair#*:} start=0
    [[ $name == rest ]] && start=8.6
    yt-dlp -q -f 'bv*[height<=480]' -o "$name.src.%(ext)s" -- "$id"
    ffmpeg -loglevel error -y -ss "$start" -i "$name".src.* -c:v libx264 -pix_fmt yuv420p -an "$name.mp4"
    rm "$name".src.*
  done
  cd ../..
  ```

### Rehearse locally (free: nothing is dialled, template drafts, no keys read)

```sh
# terminal 1, repo root: the local backend with the scripted receptionist
(cd backend && uv run python -m scripts.local_demo --port 8799 --delay 0.3)
# terminal 2, repo root: live mode, the PLAN script from clips; press s after each draft, e to end
C=$PWD/spikes/recognition/artifacts/fallback_clips   # absolute: sign_lab.sh runs the bridge from spikes/recognition
scripts/sign_lab.sh --bridge-only --model asl --port 8799 -- --video \
  $C/rest.mp4 $C/hello.mp4 $C/rest.mp4 $C/rest.mp4 $C/no.mp4 $C/tomorrow.mp4 $C/please.mp4 \
  $C/rest.mp4 $C/rest.mp4 $C/yes.mp4 $C/thankyou.mp4 $C/rest.mp4
# Call for me, attended: clips can't wait for the question, so be the receptionist yourself
(cd backend && uv run python -m scripts.sign_lab --port 8799 --receptionist manual)   # terminal 1
scripts/sign_lab.sh --bridge-only --model asl --port 8799 -- --video \
  $C/rest.mp4 $C/yes.mp4 $C/rest.mp4 --delegated --attended --name Asha    # terminal 2
# the bridge calibrates on the rest clip, then places the call; when terminal 2 prints the agent's
# opening line, type in terminal 1: We have 4 pm tomorrow. Does that work?
# the yes clip answers about 2 s after the call connects; then type: Yes, 10:30 tomorrow morning.  (the agent closes)
```

`scripts/sign_lab.sh --free --model asl` starts both in one terminal (webcam by default;
add `-- --video ...` for clips). Drop `--video ...` to sign at the webcam instead.

### Demo day: the deployed backend

`sign_lab.sh` only talks to a local backend, so run the bridge directly. The backend
address and the app token come from the team's secret store, never from this file:

```sh
cd spikes/recognition
read -r ISHARA_BACKEND               # paste https://<deployed backend>
read -rs APP_TOKEN && export APP_TOKEN   # paste the app token (not echoed, not saved)
ASL=(--live --model asl --recognizer-python .venv/bin/python --camera 0 --log)
# live mode: the Mac places the call (a real Bolna call from Bolna's number: cost heads-up first)
artifacts/bridge/.venv/bin/python mac_bridge.py --base-url "$ISHARA_BACKEND" --contact clinic --confirm-cost "${ASL[@]}"
# Call for me, attended (needs the D9 endpoints deployed)
artifacts/bridge/.venv/bin/python mac_bridge.py --base-url "$ISHARA_BACKEND" --contact clinic --confirm-cost \
  "${ASL[@]}" --delegated --attended --name "<caller name>"
```

`--call-id <id>` instead of `--contact clinic --confirm-cost` joins a call that is already
up, but the app doesn't show its call id, and joining replaces the phone's connection
(the backend keeps one app socket per call). So on demo day the Mac places its own call.
`--recognizer-python .venv/bin/python` matters: the bridge's default is the SignCLIP venv.
The bridge starts the recognizer first (2–15 s to load, measured on a busy Mac): rest both
hands for 2 s, and the call is placed only after `live recognizer ready (rest line y=…)`,
so the Mac sees signs from the first second of the call. If the recognizer fails to start,
nothing is dialled: fix it and re-run, or drop `--live ...` and type the signs. On a busy Mac
played clips fall behind real time (tracking was 3x slower than the video once), so close
heavy apps before the demo. If recognition misbehaves during the call, type the signs
(`hello`, `no tomorrow please`, …) or `a yes`; nothing is ever spoken without `s` or an answer.

### Automated check

`test_mac_bridge.ClipDrivenFallback` plays both runs against a local backend on a free
port and asserts on what the backend sent back: the drafts for the expected chips, a
`spoken` for every SEND, the agent's question answered by the yes clip (`ask_resolved`
from the user, no chip), the call notes (outcome `booked`), and that the recognizer's ready
line came before the bridge joined the call. `scripts/verify.sh` runs it as its own
"clip-driven fallback" category (about 1 minute; `light_tests.py` leaves it out); without
the venvs, model or clips that category is `SKIPPED` with what is missing.
`ISHARA_FALLBACK_CLIPS=DIR` points it at other clips with the same names.

```sh
.venv/bin/python -m unittest -v test_mac_bridge.ClipDrivenFallback
```

Measured 28 Oct on these clips (one signer, not the presenter, no Deaf users): every
script sign became the right chip (hello 0.67, no 0.96, tomorrow 0.75, please 0.95,
yes 0.70–0.72, thankyou 0.82; 0.4–0.9 s from hands down to chip), morning stayed `?`
(top-1 `table` 0.08) and the out-of-vocabulary DAILY clip stayed `?` (`every` 0.55).

## Evaluate saved videos end to end (video_eval.py)

Replays saved clips through the same live path and scores them; it never feeds labels,
audio or file names to the recognizer. Results: [video pipeline evaluation](../../docs/experiments/video-pipeline-eval.md).

```sh
artifacts/signclip/.venv/bin/python video_eval.py prepare     # local spec -> silent clip_NNN.mp4 + manifest; labels apart
artifacts/signclip/.venv/bin/python video_eval.py bundle      # references only: live cut, leave-one-out cut-offs, frozen
artifacts/signclip/.venv/bin/python video_eval.py recognize   # test clips, paced like a camera
.venv/bin/python video_eval.py score                          # per-sign table, confusions, latency p50/p95
artifacts/signclip/.venv/bin/python video_eval.py turns --turns artifacts/video_eval/turns.json
```

- The spec (`artifacts/video_eval/spec.json`, local) lists sources (file, URL, signer,
  terms, label evidence) and cuts (start, end, label, `reference` or `test`, test set).
  `prepare` strips audio, subtitles and metadata, pads 2 s of rest before and 1 s after,
  and refuses a test clip that shares a clip id, hash, source video or signer with a
  reference; `recognize` and `turns` check that again against the bundle.
- A reference whose clip the detector can't cut is kept whole (like `--manual-stop`).
- Compose and voice the turns with the backend:
  `cd ../../backend && uv run python -m scripts.compose_turns --help` (Groq and Sarvam
  cost money; calls are capped with `--max-groq` / `--max-voice`).
- Everything stays under ignored `artifacts/video_eval/`; public videos are for local
  evaluation only and are never committed.

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
