# How to test Ishara

Updated 24 October 2026. The one place that says **how** to test every layer: the exact
commands, what "pass" means, what runs by itself and what needs a person, a device or
money, and the latest measured result. [PLAN.md](../PLAN.md) owns the decisions, tasks
and gates ([§7](../PLAN.md#7-gates-go--no-go), [§8](../PLAN.md#8-testing-plan)); if
they disagree, PLAN wins. Owners: **[You]** founder, **[Mate]** teammate with the iPhone,
**[Build]** engineering, **CI** GitHub Actions on every push and PR.

Rule of thumb: everything that can run without a phone call, a camera or a person runs
in `scripts/verify.sh`, and CI runs all of it except the iOS app tests (Swift packages
only when `ios/**` changed). Paid calls, recording sessions and the device are human
runs with written, dated results.

```
 free, automated (verify.sh)                 free, by hand              paid or device (needs a go-ahead)
 ────────────────────────────────────────    ───────────────────────    ─────────────────────────────────
 L1 unit/contract ─▶ L2 backend E2E           L6 app ↔ local backend     L8 Sign Lab (Groq, Sarvam)
 L4 iOS packages     (FakeBolna)              L7 iOS visual review       L9 public-video eval (Groq, Sarvam)
 L5 iOS app tests ─▶ L3 local demo server                                L10 recognition sessions (G2)
                                                                         L11 parity P3 (G3)
                                                                         L12 live Bolna call V4/A3 (G1)
                                                                         L13 iPhone T1–T3 (G4) ─▶ L14 demo
```

## 1. Layers at a glance

| # | Layer | Purpose | Runs where | Cost | Who | Latest result |
|---|---|---|---|---|---|---|
| L1 | Unit and contract | every module and safety rule on its own; protocol mirror; spikes | CI + `verify.sh` | free | [Build] | 24 Oct, `main @ 79266c7`: backend **813 / 813** passed, ruff clean; call_flow **13 / 13**; recognition light **209 / 209**; Heroku scripts **14 / 14**; shellcheck clean. CI green on the same commit |
| L2 | Backend E2E with FakeBolna | the PLAN §1 call and the safety edge cases through the real app, Bolna faked | CI + `verify.sh` (inside the backend `pytest`) | free | [Build] | 24 Oct: **11 / 11** (part of the 813) |
| L3 | Local demo server | the real backend on this Mac with a scripted Bolna and receptionist, for the app or the Mac bridge | server tests in CI; running it is by hand | free | [Build] | 24 Oct: `test_local_demo.py` **10 / 10** in CI |
| L4 | iOS packages | detector, matcher, call session (`TurnStore`), sign pipeline, without the app | `verify.sh`; CI when `ios/**` changes | free | [Build] | 24 Oct: CallSession **164 / 164**, RecognitionCore **92 / 92**, SignPipeline **66 / 66**; SignPipelineMediaPipe 1 skipped on macOS (**8 / 8** on the simulator, PR #27) |
| L5 | iOS app unit + UI tests (fake driver) | view model, live driver against an in-memory backend, the whole §1 call clicked through on the fake driver | `verify.sh` only (**not in CI**: CI has no simulator job) | free | [Build] | 24 Oct, iPhone 17 / iOS 27.0: `IsharaTests` **139 / 139**; `IsharaUITests` **4 passed, 1 skipped** of 5 (the skip is L6) |
| L6 | App ↔ local backend E2E | the iOS app's live driver against the real backend code (L3), nothing dialled | by hand, opt-in UI test | free | [Build] | 24 Oct (PR #27): **passed**, [evidence](experiments/evidence/app-backend-e2e-24oct/README.md). Re-run 24 Oct on `79266c7`: **fails 0 / 1**, the test's check predates the holding line ([issue #41](https://github.com/BishalJena/ishara/issues/41), [§2 L6](#app--local-backend-end-to-end)) |
| L7 | iOS visual review | every screen and state in light, dark, large text and on the small phone | by hand (fixtures + screenshots) | free | [Build] | 24 Oct: 19 findings + 6 polish; **F1–F9 fixed** in #37–#40, [review](experiments/evidence/ios-visual-review-24oct/README.md), [fixes](experiments/evidence/ios-fixes-verified-24oct/README.md) |
| L8 | Sign Lab | Mac webcam signs → real recognizer → real Groq drafts → real Sarvam voice on the Mac speakers; no call | by hand; its code is CI-tested with fakes | small (Groq per chip change, Sarvam ₹0.1–0.5 per line) | [You] | 24 Oct smoke (PR #30): 1 Groq draft in 0.23 s, passed the validator; Sarvam 1.82 s, `afplay` exit 0. **Webcam run with the founder's takes: not yet** |
| L9 | Public-video pipeline eval | saved clips through the live recognizer, composer and voice, scored against hidden labels | by hand | small (17 Groq + 8 Sarvam requests last time) | [Build] | 24 Oct: cross-signer set A **0 / 24** chips (0 wrong), set B **4 / 18** correct, **1** wrong; 5 / 5 turns stayed silent; [report](experiments/video-pipeline-eval.md) |
| L10 | Recognition sessions R1, R3, R4 | the founder's own signs: calibration sets the cut-off, the final session is scored once | by hand | free | [You] | not run |
| L11 | Parity P1 / P3 | Core ML encoder vs PyTorch (P1); simulator pipeline vs Mac (P3) | by hand | free | [Build] | P1, 23 Oct (PR #21): **47 / 47** clips pass with `.cpuAndGPU`, **0 / 47** with the Neural Engine. P3: not run |
| L12 | Live Bolna call V4, A3 | exact text spoken on a real call, timings, B24/B25 | by hand | paid (V4 about ₹20–30) + explicit go-ahead | [Build + Mate] | **not run**. Executed so far: Heroku `/health`, custom model registered, live `[silence]` → holding line, no token → 401 (23 Oct) |
| L13 | Real iPhone T1–T3 | camera, voice and captions together on the device | by hand | free (T2 places paid calls) | [Mate + You] | not run (iPhone from Thu 29) |
| L14 | Demo rehearsal D2 | full script × 3, backup video | by hand | paid calls | [You + Mate] | not run |

## 2. Layer by layer

Each block: the command, what pass means, and anything that trips people up. Paths are
from the repo root unless the command starts with `cd`.

### L1 Unit and contract

```sh
scripts/verify.sh                         # everything below in one go; --keep-going to see every failure
cd backend && uv run ruff format --check . && uv run ruff check . && uv run pytest -q
python3 -m unittest discover -s spikes/call_flow -p 'test_*.py'
cd spikes/recognition && .venv/bin/python -m unittest test_retrieval test_detector test_detect_clips \
  test_mac_bridge test_live_source test_record_session test_video_eval
python3 -m unittest discover -s backend/scripts -p 'test_*.py'    # Heroku scripts, fake heroku CLI
shellcheck -x scripts/*.sh backend/scripts/*.sh
```

- **Pass:** every command exits 0; `verify.sh` ends with `verify: OK`. A `SKIPPED` line
  names what's missing (no venv, no Xcode); it is not a pass for that layer.
- The recognition light tests need `spikes/recognition/.venv` or `.venv-light`
  (`uv venv --python 3.11 .venv-light && uv pip install --python .venv-light/bin/python -r requirements-light.txt`).
  `test_mini` needs torch and stays local; so does `ml/coreml/`.
- The backend tests never read the real `.env`, and `tests/conftest.py` refuses DNS
  lookups of non-loopback hosts, so no test can reach a paid API.

### L2 Backend E2E with FakeBolna

Same `pytest` run (`backend/tests/e2e/test_demo_script.py`). `create_app` with the real
CallManager, custom-LLM router and template composer; Bolna is `backend/fakes/fake_bolna.py`,
which follows Bolna's docs (request shape, `{{var}}` filling, node moves, end of call).

- **Pass:** 11 / 11. What each test guards is in [§4](#4-what-the-e2e-suite-proves-and-what-it-cant).
- Free smoke against a running server instead of ASGI:
  `FakeBolna(token, httpx.AsyncClient(base_url=...))` from a Python shell.

### L3 Local demo server

```sh
cd backend
uv run python -m scripts.local_demo            # http://127.0.0.1:8000, token ishara-local-demo
uv run python -m scripts.local_demo --b24      # receptionist talks over the first SEND
APP_TOKEN=ishara-local-demo uv run python -m scripts.fake_app \
  --base-url http://127.0.0.1:8000 script --contact clinic --confirm-cost   # scripted app, still free here
```

- **Pass:** the server prints `agent says:` for the disclosure, each approved reply
  (exact text) and the goodbye, and the receptionist's two lines after the first and
  second spoken replies; nothing else is said except the holding line after 15 s of
  silence (scaled by `--delay`). `--b24`: the first SEND ends `not delivered`, a re-SEND
  is spoken once.
- No key is set even if one is exported, so drafts are templates and nothing reaches
  Bolna, Groq or Sarvam. CI covers it with `tests/test_local_demo.py` (full §1 script
  and B24). Details: [backend/README.md](../backend/README.md#local-demo-no-bolna-no-cost).

### L4 iOS packages

```sh
for p in CallSession RecognitionCore SignPipeline SignPipelineMediaPipe; do swift test --package-path ios/Packages/$p; done
```

- **Pass:** 0 failures. `SignPipelineMediaPipe` only builds for iOS, so on macOS its one
  test skips; run it on a simulator with
  `xcodebuild test -scheme SignPipelineMediaPipe -destination 'platform=iOS Simulator,name=iPhone 17'`
  from its package folder (the Holistic photo tests need `Scripts/download_holistic_test_assets.sh`).
- If `xcode-select` points at the Command Line Tools, prefix
  `DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer` (there is no XCTest otherwise).
- CI runs this on `macos-26` only when `ios/**` or the workflow changed.

### L5 iOS app unit + UI tests (fake driver)

```sh
xcodebuild -project ios/Ishara.xcodeproj -scheme Ishara \
  -destination 'platform=iOS Simulator,name=iPhone 17' test
# just the unit tests: add -only-testing:IsharaTests
# the small phone: -destination 'platform=iOS Simulator,name=iPhone 17e'
```

- **Pass:** `** TEST SUCCEEDED **`, every UI test passed except `LocalBackendCallUITests`,
  which skips unless L6 is set up. `DemoCallUITests` walks the whole §1 call on the fake
  driver at `-IsharaFakeTimeScale 0.5` (about a minute), at default text and at AX-L, and at
  every SEND asserts the draft is fully on screen above SEND; a fixture test checks the
  sentence above SEND/STOP at AX-L and AX-XXXL.
- **Not in CI.** `verify.sh` runs it (it boots the simulator first). Run it before
  merging anything under `ios/`.
- Regenerate the project after editing `ios/project.yml`: `xcodegen generate --spec ios/project.yml`.

### App ↔ local backend end to end

L6. The iOS app's live driver against L3, nothing dialled.

```sh
# 1. ios/Ishara/Config/Secrets.xcconfig (gitignored):
#      ISHARA_BACKEND_URL = http:/$()/127.0.0.1:8799
#      ISHARA_APP_TOKEN = ishara-local-demo
# 2. server
(cd backend && uv run python -m scripts.local_demo --port 8799 > /tmp/local-demo.log)
# 3. test, in another terminal
TEST_RUNNER_ISHARA_LOCAL_BACKEND=1 TEST_RUNNER_ISHARA_LOCAL_BACKEND_LOG=/tmp/local-demo.log \
  xcodebuild -project ios/Ishara.xcodeproj -scheme Ishara \
  -destination 'platform=iOS Simulator,name=iPhone 17' \
  -only-testing:IsharaUITests/LocalBackendCallUITests test
```

- **Pass:** the test passes, and the server log shows the §1 lines in order with nothing
  spoken before each SEND, the removed `afternoon` and the `[?]` never spoken, and only
  the fixed agent lines (disclosure, holding line, goodbye) said without a SEND.
- By hand instead: launch the app with `-IsharaDriver live -IsharaRecognition scripted`
  and use the replay menu for chips.
- Latest: passed on 24 Oct with PR #27 ([evidence](experiments/evidence/app-backend-e2e-24oct/README.md)).
  **Re-run 24 Oct on `main @ 79266c7`: fails, 0 / 1**, with `--delay 0.3` before turn 1
  and with the default delay after turn 2. Since #37 the scripted Bolna plays the holding
  line after 15 s × `--delay` of silence, and the test counts it as speech before SEND.
  The backend behaviour is right; the test's check is out of date:
  [issue #41](https://github.com/BishalJena/ishara/issues/41). Until it's fixed, read
  the server log by hand: only the disclosure, holding lines and goodbye may appear
  without a SEND.

### iOS visual review

L7. Screenshots of every state, read against [WORKFLOW.md](WORKFLOW.md), the
[board](architecture/README.md) and the safety rules.

```sh
xcrun simctl status_bar booted override --time 9:41
xcrun simctl launch --terminate-running-process booted ai.ishara.demo -IsharaFixture signing
xcrun simctl io booted screenshot /tmp/ishara-signing.png
# large text: add -UIPreferredContentSizeCategoryName UICTContentSizeCategoryAccessibilityL
# dark mode:  xcrun simctl ui booted appearance dark
```

- Fixture names are in [ios/README.md](../ios/README.md#run) (`home`, `getReady`,
  `signing`, `speaking`, `delivered`, `notDelivered`, `ended`, `connectionLost`,
  `composing`, `stopped`, `stopTooLate`, `deliveredDespiteStop`, `backendError`,
  `endedNoCaptions`, `hangUpUnconfirmed`).
- **Cover:** each fixture in light, dark and AX-L on iPhone 17, and the call screens on
  iPhone 17e; plus the walked call at 1× and 0.5×.
- **Pass:** on every screen where SEND or STOP is enabled, the exact sentence it acts on
  is fully visible; the calling-number disclosure is on Home and Get ready; nothing says
  "delivered" for text that wasn't spoken; no developer text on user screens. Each
  problem gets an ID, a severity and a screenshot, like
  [the 24 Oct report](experiments/evidence/ios-visual-review-24oct/REPORT.md).

### L8 Sign Lab (Mac webcam, real Groq and Sarvam)

```sh
cd spikes/recognition
.venv/bin/python record_session.py --camera 0                                          # 3 takes × 12 signs, ~10 min
artifacts/signclip/.venv/bin/python retrieval.py export-bundle --encoder signclip --provisional
cd ../.. && scripts/sign_lab.sh            # paid: Groq per chip change, Sarvam per spoken line
scripts/sign_lab.sh --free                 # templates, no voice, no cost
# type the receptionist's lines yourself (two terminals):
scripts/sign_lab.sh --backend-only --receptionist manual
scripts/sign_lab.sh --bridge-only
```

- **Pass (a try, not a measurement):** each signed sign shows as the right chip or `?`,
  never a wrong chip; `draft (llm …)` keeps every chip's meaning and adds no day, time,
  number or name (otherwise `fallback:` shows the validator's reason and a template is
  used); nothing is voiced before SEND; the voice says exactly the approved text.
- The provisional bundle is **not** Gate 2: same session, no negatives, optimistic
  cut-offs. Keys are read only from the repo-root `.env` and only for the paid flags.
- Write what you saw (signs tried, chips, drafts, timings) in
  [recognition.md](experiments/recognition.md) with the date.

### L9 Public-video pipeline eval

```sh
cd spikes/recognition        # local spec at artifacts/video_eval/spec.json, media stays local
artifacts/signclip/.venv/bin/python video_eval.py prepare
artifacts/signclip/.venv/bin/python video_eval.py bundle       # references only; cut-offs frozen here
artifacts/signclip/.venv/bin/python video_eval.py recognize    # test clips, paced like a camera
.venv/bin/python video_eval.py score
artifacts/signclip/.venv/bin/python video_eval.py turns --turns artifacts/video_eval/turns.json
cd ../../backend && uv run python -m scripts.compose_turns --help   # paid; cap with --max-groq / --max-voice
```

- **Pass:** the rules in [§6](#6-rules-that-stop-a-recognition-test-from-cheating)
  held, and the report gives counts with denominators per sign and set, wrong chips
  separately from `?`, and latency p50/p95. A cross-signer run measures the mechanics,
  not demo accuracy.
- Re-run it with the founder's own takes as references and a separate session as the
  test set; that is the number that matters (next step in
  [the report](experiments/video-pipeline-eval.md#next-steps)).

### L10 Recognition sessions (R1, R3, R4 → Gate 2)

```sh
cd spikes/recognition
.venv/bin/python pilot_capture.py capture --signer demo --session enrollment-01 --split enrollment --concept hello --takes 3 --camera 0
.venv/bin/python pilot_capture.py review --id CLIP_ID
.venv/bin/python pilot_capture.py verify --id CLIP_ID --note "sign form checked against <reference>"
artifacts/signclip/.venv/bin/python retrieval.py calibrate --encoder signclip     # R3 session only
artifacts/signclip/.venv/bin/python retrieval.py evaluate --encoder signclip --fresh   # R4, once
artifacts/signclip/.venv/bin/python retrieval.py export-bundle --encoder signclip
```

- **Pass R2b (calibration):** the frozen cut-off accepts ≥ 60% of attempts for every
  sign, 0 wrong accepts, 0 accepts on the 20 negatives; a reject-all cut-off fails.
- **Pass G2 (R4 final, evaluated once):** ≥ 9/10 per sign, 0 wrong accepts, 0 accepts on
  the 50 negatives, < 2 s from sign end to chip, live.
- Runbook: [spikes/recognition/README.md](../spikes/recognition/README.md).

### L11 Parity (P1, P3 → Gate 3)

```sh
cd ml/coreml && .venv/bin/python parity.py && .venv/bin/python -m unittest -v test_contract   # P1
```

- **Pass P1:** cosine ≥ 0.999 to PyTorch on every saved clip with `.cpuAndGPU`.
- **Pass P3:** the simulator pipeline and the Mac give the same accepted label (or `?`)
  on every calibration clip; re-embed the enrollment references with the iOS extractor
  first. Setup: [ml/coreml/README.md](../ml/coreml/README.md).

### L12 Live Bolna call (V4, A3 → Gate 1)

```sh
cd backend
uv run python -m scripts.voice_spike --base-url https://<app>.herokuapp.com \
    --contact clinic --confirm-cost          # V4: the nine checks, end_call last
uv run python -m scripts.fake_app --base-url https://<app>.herokuapp.com \
    script --contact clinic --confirm-cost   # A3-style §1 script with a latency table
```

- **Before:** explicit go-ahead from the founder for this call, a cost heads-up (Bolna
  about ₹5.5/min plus telephony; V4 about ₹20–30), the teammate's consent, the number
  only in `ALLOWED_RECIPIENTS` on Heroku, synthetic appointment details.
- **Pass G1:** exact text spoken once per SEND, nothing before SEND, double SEND speaks
  once, holding line after silence, captions reach the backend. Record SEND → `spoken`
  (the tool) and SEND → first audio (a stopwatch) in
  [voice.md](experiments/voice.md), which the runner appends to.

### L13 Real iPhone (T1–T3 → Gate 4) and L14 demo

- **T1:** install with Xcode and the dev team; record the iOS version; grant camera; turn
  on Add Audio in Calls. Check what the simulator can't: live mirrored preview, permission
  prompt and Open Settings (F2), Holistic + encoder latency.
- **T2:** the §1 script live twice on the phone camera, then the edge-case run: long
  pause, fidgeting, wrong chip, out of frame, double SEND, receptionist interrupting,
  network off, End. **Pass G4:** the recipient repeats each sentence exactly, twice.
- **T3 (bonus):** Path A own-number call with a Sarvam clip.
- **D2:** script × 3 and a backup video (kept outside Git).
- Results go in `docs/experiments/device.md` (created with the first run).

## 3. Safety rules → tests

Every rule has a test that fails if the rule is removed (checked by mutation, [§5](#5-mutation-testing)).

| Rule | Backend | App / packages | Mac bridge | Live check |
|---|---|---|---|---|
| Nothing is spoken unless the user taps SEND | `e2e: test_nothing_is_spoken_before_send`; `test_sessions.py: test_claim_false_for_unapproved_turn`, `test_mark_spoken_only_after_claim` | `TurnStoreTests.testNotDeliveredOffersResendWithoutSendingAnything`; `DemoCallUITests` (draft visible above SEND at each SEND); `LocalBackendCallUITests` reads the server log | `test_no_draft_means_nothing_to_send`, `test_stop_never_queues_text` | V4 steps 1–2 |
| Approval is single use | `test_sessions.py: test_approval_is_single_use`, `test_claim_true_once_with_exact_text_only`; `e2e: test_double_send_speaks_once`, `test_duplicate_event_delivery_speaks_once` | `TurnStoreTests.testDoubleSendApprovesOnce`; `ActiveCallViewModelTests.testSendIsSingleUseAndWipesChipsAndDraft` | `test_send_approves_the_draft_once_and_starts_a_new_turn` | V4 step 5 |
| A new turn makes the old approval stale | `test_sessions.py: test_new_turn_revokes_unclaimed_approval`; `e2e: test_stale_turn_approval_is_not_spoken` | `ActiveCallViewModelTests.testDraftForStaleTurnIsIgnored` | | |
| `[?]` is shown but never sent or spoken | (the app never sends it) | `TurnStoreTests.testUnsureChipIsShownButNeverSent`, `testOnlyUnsureChipsSendNothing`; `SegmentClassifierTests` (low confidence, no bundle, no encoder → `?`) | `test_unsure_is_shown_but_never_sent`, `test_signs_send_chips_without_unsure_entries` | T2 |
| Unsure or failed delivery stays silent; B24 never speaks late | `e2e: test_send_during_receptionist_speech_is_not_delivered_then_resent_once`; `test_sessions.py: test_failed_delivery_blocks_late_claim` | `TurnStoreTests.testNotDeliveredOffersResendWithoutSendingAnything` | `test_not_delivered_waits_and_resend_uses_a_new_turn_id`, `test_late_spoken_cancels_the_pending_resend` | V4 step 8 |
| Ended or lost calls stay silent | `e2e: test_approve_after_end_is_not_spoken`, `test_end_while_reply_is_in_flight_is_not_spoken`; `test_webhook_end_revokes_pending_approval` | `TurnStoreTests.testNothingIsSentAfterEnd`, `testNothingIsSentWhileDisconnected` | `test_ended_call_drops_pending_and_awaited_resends`, `test_run_stops_silently_when_the_backend_hangs_up` | T2 network off |
| Only allowlisted contacts are called | `test_calls.py: test_unknown_contact_is_forbidden_and_bolna_untouched`; `test_main.py: test_empty_allowlist_boots_and_forbids_every_contact`, `test_malformed_allowlist_fails_at_boot`; `e2e: test_unknown_contact_is_refused_and_never_dialled` | | | |
| No paid call by surprise | tools and spike runners refuse without `--confirm-cost` (`test_voice_spike.py`, `test_fake_app.py`) | the app's default is the fake driver; `-IsharaDriver live` opts in | `test_start_call_needs_confirm_cost_before_any_request`, `test_main_refuses_to_dial_without_confirm_cost` | |
| Only the app token starts calls and opens sockets | `test_calls.py: test_start_call_requires_app_token`, `test_socket_rejects_bad_token`; `e2e: test_start_call_without_app_token_is_refused` | | | |
| The webhook needs its own secret | `test_calls.py: test_webhook_secret_checked` (a wrong secret, the app token and the custom-LLM token all get 404) | | | |
| The LLM may reword but not add facts | `test_validator.py` (invented day, time, number, name; missing "no"); `test_composer.py: test_timeout_falls_back_to_template_within_budget` | | | V5b gap: added agreement still passes ([PLAN V5b](../PLAN.md#sun-25-oct-composer-calibration)) |

## 4. What the E2E suite proves (and what it can't)

| Test (`tests/e2e/test_demo_script.py`) | Safety rule it guards |
|---|---|
| `test_plan_demo_script_end_to_end` | §1 turns 0–6: disclosure, captions, 3b wrong chip removed, exact text, goodbye, and the whole transcript the app sees in order (agent and receptionist captions) |
| `test_nothing_is_spoken_before_send` | Nothing is spoken unless the user taps SEND |
| `test_double_send_speaks_once`, `test_duplicate_event_delivery_speaks_once` | Approval is single use (app side and Bolna side) |
| `test_stale_turn_approval_is_not_spoken` | A new turn wipes the old approval |
| `test_send_during_receptionist_speech_is_not_delivered_then_resent_once` | B24: no `spoken` → `not_delivered`; a dead turn never speaks later; re-SEND speaks once |
| `test_each_silence_shows_the_holding_line_as_an_agent_caption` | Every `[silence]` gets the holding line, shown as an agent caption, never as the receptionist's words |
| `test_end_while_reply_is_in_flight_is_not_spoken`, `test_approve_after_end_is_not_spoken` | Ended calls stay silent |
| `test_unknown_contact_is_refused_and_never_dialled`, `test_start_call_without_app_token_is_refused` | Only allowlisted, authenticated calls |

FakeBolna follows Bolna's docs, not observed behaviour. It can't prove B23 (graph agent
with a custom LLM during a call), real latency, Deepgram transcripts or Sarvam audio. V4 does that.

## 5. Mutation testing

PLAN §8: every safety rule needs a test that fails if the rule is removed. Target: more
than 90% of mutants killed on each safety module; every survivor is either a missing
test (write it) or an equivalent mutant (say why in the PR). Run before G1 and after any
change to a safety module.

**Backend, with [mutmut](https://github.com/boxed/mutmut)** (dev dependency; `[tool.mutmut]`
in `backend/pyproject.toml` lists the modules; `backend/mutants/` is git-ignored):

```sh
cd backend
rm -rf mutants && uv run mutmut run --max-children 4   # more children crash workers on macOS ("segfault")
uv run mutmut results --all true                       # status of every mutant
uv run mutmut show <mutant-name>                       # the diff of one survivor
```

Last run (23 Oct 2026, PR #26; the first run was 86.3% across the five target modules,
the tests added from its survivors raised it to):

| Module | Rule | Killed / mutants | Survivors |
|---|---|---|---|
| `app/sessions.py` | single-use approval, stale turn, ended call, single claim | 102 / 104 (98.1%) | 2 equivalent: exception text, phase of a turn already dropped from flight |
| `app/calls.py` | allowlist, approval → event, delivery timer, `not_delivered`, webhook | 355 / 384 (92.4%) | 29: error and exception message texts (10), socket `open` flags after a disconnect (6), timer cancellation (7, equivalent: an expired timer checks the turn id), task set retention (2), default timeout, bearer parsing edge cases (2), exception args |
| `app/custom_llm.py` | speak only after `claim_reply`, routing first, `[silence]`, captions | 131 / 133 (98.5%) | 2 equivalent: join separator before a substring check, an `assert` |
| `app/validator.py` | no invented day/time/number/name, chip meanings kept, 25-word cap | 228 / 281 (81.1%); 228 / 238 (95.8%) without the 43 import-time mutants | 43 in `_temporal_table`, which runs at import so mutmut can't switch it; a hand pass of 20 mutants on that table killed 18 (the other 2 are a redundant row and a stricter-only regex). 10 more are equivalent |
| `app/tts.py` | one voice per `turn_id`, failures release the turn | 18 / 18 (100%) | none |
| `app/contacts.py` | `contact_id=+E164` parsing, no number in errors | 18 / 19 (94.7%) | 1 equivalent (`rpartition`) |
| `app/markers.py` | marker parsing | 57 / 58 (98.3%) | 1 equivalent (both groups are in one optional group) |

Since then `calls.py` gained the webhook's own secret and agent captions (#26 follow-up,
#37), each with tests; mutmut has not been re-run on them. **Re-run before G1.**

**Hand-made mutants** (rule removed, limit shifted or branch inverted one at a time,
then the suite run) where no mutation tool is set up:

| Code | PR | Killed / mutants |
|---|---|---|
| Sarvam client + `/tts` | #7 | 36 / 36 |
| Composer + Groq client; validator | #10 | 17 / 17; 35 / 35 after one new test |
| Custom-LLM endpoint and models | #13 | 42 / 42 (two earlier survivors fixed) |
| Bolna client, CLI, agent builder | #14 | 19 / 19 |
| Call sessions and webhook | #16 | 44 / 47 at first; 2 survivors fixed, 1 equivalent |
| Mac bridge | #9 | 30 / 30 |
| CallSession package (Swift) | #20 | about 50, all killed |
| App view model safety rules | #22 | 11 / 11 |
| RecognitionCore (detector, matcher) | #23 | about 45; the one survivor is equivalent |
| `live_source` guards | #25 | 15, all but 1 equivalent; 3 / 3 subprocess mutants |
| Recording session; provisional bundle | #32 | 14 / 14; 12 / 12 |
| Sentence above SEND (F3) | #40 | 2 / 2 targeted (a 0.3 sentence cap; no chip scroll) |

## 6. Rules that stop a recognition test from cheating

Used in the [video eval](experiments/video-pipeline-eval.md#how-cheating-was-prevented)
and required for R3/R4 and any later recognition number.

| Rule | How it is enforced |
|---|---|
| The recognizer sees silent frames only | ffmpeg strips audio, subtitles, chapters and metadata; `ffprobe` shows one video stream; the recognizer reads MediaPipe landmarks only (no OCR, audio or transcript in the path) |
| No label leaks into the pipeline | neutral, shuffled clip ids (`clip_001` …); the manifest refuses a `label` key or a non-neutral name (tested); labels live in a separate file read only by `bundle` and `score`; `recognize` and `turns` take no labels |
| No clip is its own reference | `assert_no_leakage` refuses any shared clip id, content hash, source video or signer between references and tests, at `prepare` and again before every run; `recognition_data.validate_records` checks session, source and hash across splits |
| Cut-offs are never tuned on test clips | leave-one-out on the references (or the calibration session) only, frozen before the first test clip is replayed, never changed afterwards; `evaluate` and the calibrated export refuse provisional cut-offs |
| The final test is run once | R4 is evaluated once; if it fails, it becomes development data and a new final session is recorded |
| No hand-edited chips | chips are exactly the recognizer's accepted signs; `?` never reaches the composer; drafts from ground-truth chips are labelled "oracle" |
| Report every outcome | counts with denominators per sign: correct, wrong, `?`, no segment; wrong chips are never folded into "unsure" |

## 7. Gates → evidence

| Gate | Automated evidence (must be green first) | Human evidence | Pass recorded in | Status (24 Oct) |
|---|---|---|---|---|
| **G1** Voice | L2 E2E: exact text once, nothing before SEND, duplicate delivery once, B24 → `not_delivered`, silence → holding line, captions reach the app | V4 call: steps 1–9 with SEND → first audio times | [voice.md](experiments/voice.md) | automated green; V4 not run |
| **G2** Recognition | matcher and detector unit tests; frozen cut-off checked in | R4 final session: ≥ 9/10 per sign, 0 wrong accepts, 0 accepts on 50 negatives, < 2 s live | [recognition.md](experiments/recognition.md) | automated green; R1/R3/R4 not run |
| **G3** On-device | P3 parity: same label (or `?`) on every calibration clip, Mac vs simulator | spot-check the parity report | [recognition.md](experiments/recognition.md) | P1 done (47 / 47 on `.cpuAndGPU`); P3 not run |
| **G4** Real call | whole `verify.sh` green on the installed commit | T2 full script live twice; recipient repeats each sentence exactly | `docs/experiments/device.md` | not run |

## 8. Recording results

- Write **what ran**: date, commit, device or simulator, command, counts **with
  denominators**, timings, and what was not run. Keep it apart from what docs claim
  ("documented" vs "executed"), as in [video-pipeline-eval.md](experiments/video-pipeline-eval.md).
- Raw outputs go in `docs/experiments/evidence/<topic>-<date>/` with a README table
  (file → what it shows). Only our own outputs: no third-party media, no keys, phone
  numbers, account ids or tokens, no absolute local paths. Screenshots as downscaled
  JPEGs (`sips -s format jpeg -s formatOptions 70 -Z 800 in.png --out out.jpg`); keep a
  folder under about 8 MB. Logs as `.txt` (`*.log` is ignored).
- Before committing evidence, scan it: no match for `gsk_`, `HRKU-`, `sk-`, `Bearer `,
  `+91` numbers, `/Users/<name>/`, or any value from your `.env`.

Evidence so far:

| Folder | What |
|---|---|
| [video-pipeline-eval](experiments/evidence/video-pipeline-eval/README.md) | L9 per-clip results, scores, turns, composer drafts, Sarvam audio |
| [ios-visual-review-24oct](experiments/evidence/ios-visual-review-24oct/README.md) | L7 report F1–F19 and its screenshots |
| [ios-fixes-verified-24oct](experiments/evidence/ios-fixes-verified-24oct/README.md) | L7 before/after for F1–F9 (PRs #37–#40) |
| [app-backend-e2e-24oct](experiments/evidence/app-backend-e2e-24oct/README.md) | L6 screenshots and the server log of what was "spoken" |

## 9. Before merging

1. `scripts/verify.sh --keep-going` ends with `verify: OK`, with no `SKIPPED` for a part
   you changed (iOS changes need the app category to PASS: CI doesn't run it).
2. CI is green on the PR (`backend`, `spikes-light`, `scripts`, and `swift-packages`
   when `ios/**` changed).
3. The branch is up to date with `main` (`git fetch origin && git merge origin/main`),
   and checks were re-run after the update.
4. A changed safety rule has a test that fails without it; for a backend safety module,
   mutmut was re-run and survivors explained in the PR.
5. Paid or device runs are written down (§8) with the date; nothing paid ran without
   the founder's go-ahead.
6. Docs that link to each other still resolve (relative links and anchors).

## 10. Day-by-day checklist

| Day | Automated (every push) | Human / paid |
|---|---|---|
| **Fri 23** | backend foundation tests; fake Bolna tests; E2E skips cleanly | H1 keys in `.env`, H2 teammate number in config only |
| **Sat 24** | V2 lands → custom-LLM tests; E2E starts running for the parts that exist | V4 spike call (cost heads-up first), results in `voice.md`; **G1**; R1 enrollment |
| **Sun 25** | V5 composer: template fixture per script turn, validator (invented time, missing "no", > 25 words), Groq timeout → template | R3 calibration session; R2b cut-off frozen |
| **Mon 26** | V6 lands → **E2E fully green**; mutmut on safety modules > 90% | R4 final session, evaluated once; **G2** |
| **Tue 27** | Swift detector/matcher tests; P3 parity run | **G3** review |
| **Wed 28** | `xcodebuild test` on the app with the replay recognizer; E2E still green | A3 real call from the simulator, script twice |
| **Thu 29** | full `scripts/verify.sh` green on the installed commit | T1 install, T2 live script ×2 + edge-case run, T3 Path A bonus; **G4** |
| **Fri 30** | only fixes for Thursday failures, each with a regression test | D2 rehearse ×3, backup video |
| **Sat 31** | final `scripts/verify.sh` on the submitted commit | D4 submit (confirm cutoff time and timezone) |
