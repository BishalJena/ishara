# Ishara automated test plan

Updated 23 October 2026. Turns [PLAN.md §8](../PLAN.md#8-testing-plan) and the gates in
[§7](../PLAN.md#7-gates-go--no-go) into commands, files and owners. PLAN.md wins if they
disagree. Owners: **[You]** founder, **[Mate]** teammate with the iPhone, **[Build]**
engineering, **CI** runs on every push.

Rule of thumb: everything that can run without a phone call, a camera or a person runs
in CI. Paid calls, recording sessions and the device are human runs with written results.

## 1. What runs where

| Layer (§8) | What | Command | Files | Automated? | Owner |
|---|---|---|---|---|---|
| 1 Unit: backend | config, auth, protocol, markers, composer (templates, validator, Groq timeout fallback), allowlist, single-use approval, stale turns, custom LLM | `cd backend && uv run ruff format --check . && uv run ruff check . && uv run pytest -q` | `backend/tests/test_*.py` | ✅ CI | [Build] |
| 1 Unit: fake Bolna | the fake itself: request shape, `{{var}}` filling, node moves, B24 skip, duplicates, end of call | same `pytest` run | `backend/fakes/`, `backend/tests/test_fake_bolna.py` | ✅ CI | [Build] |
| 1 E2E: demo script | §1 script and safety edge cases through `create_app` with the real CallManager, custom-LLM router and template composer, Bolna played by `FakeBolna` | same `pytest` run (`tests/e2e/`) | `backend/tests/e2e/test_demo_script.py` | ✅ CI, skips with a named reason until V2, V5 and V6 are merged | [Build] |
| 1 Unit: spikes | recognition data, retrieval, call-flow mock, Bolna probe parsing | `python3 -m unittest discover -s spikes/call_flow -p 'test_*.py'`; in `spikes/recognition`: `.venv/bin/python -m unittest -v test_mini test_retrieval` | `spikes/*/test_*.py` | ✅ CI | [Build] |
| 1 Unit: Swift | detector boundaries, matcher cut-off, call-session client, protocol mirror | `swift test` in each `ios/Packages/*` | `ios/Packages/*/Tests/` | ✅ CI (macOS runner) | [Build] |
| 1 App build | app target compiles, UI flow on fake data | `xcodebuild test -scheme Ishara -destination 'platform=iOS Simulator,name=iPhone 17'` | `ios/Ishara/` | ✅ CI (macOS runner) | [Build] |
| All of the above | one entry point | `scripts/verify.sh` | `scripts/verify.sh` | ✅ CI and before every commit | [Build] |
| 2 Recognition | calibration session sets the cut-off; final session evaluated once | `pilot_capture.py` capture, then the eval command in `spikes/recognition/README.md` | `docs/experiments/recognition.md` | ❌ human: R1, R3, R4 | [You] |
| 3 Voice | exact text, SEND → first audio, double SEND, STOP, silence, B24, B25 on a real call | `backend/scripts/voice_spike.py` (Bolna side) + `backend/scripts/fake_app.py` (plays the app over WS) | `docs/experiments/voice.md` | ❌ human: V4 (paid, needs the go-ahead) | [Build + Mate] |
| 3 Voice smoke (free) | the same FakeBolna steps against a running backend instead of ASGI | `FakeBolna(token, httpx.AsyncClient(base_url=...))` from a Python shell | `backend/fakes/fake_bolna.py` | ⚠️ manual, no Bolna cost | [Build] |
| 4 Simulator | saved videos through the iOS pipeline vs the Mac (P3); full app flow with a real call (A3) | parity script in `ml/coreml/`; A3 by hand | `docs/experiments/recognition.md` | ⚠️ parity automated, A3 human (paid) | [Build] |
| 5 Real iPhone | camera + voice + captions; edge-case run | by hand (T1, T2, T3) | `docs/experiments/device.md` | ❌ human | [Mate + You] |
| 6 Demo | full script × 3, backup video | by hand (D2) | video file outside Git | ❌ human | [You + Mate] |

`backend/scripts/*`, `scripts/verify.sh` and `ios/Packages/*` land in their own branches;
until then the rows above describe the target, not the current tree.

## 2. Gates → evidence

| Gate | Automated evidence (must be green first) | Human evidence | Pass recorded in |
|---|---|---|---|
| **G1** Voice (Sat 24) | E2E: exact text spoken once, nothing before SEND, duplicate delivery speaks once, B24 → `not_delivered`, silence → holding line, captions reach the app | V4 call: steps 1–9 with SEND → first audio times | `docs/experiments/voice.md` |
| **G2** Recognition (Mon 26) | matcher and detector unit tests; frozen cut-off value checked in | R4 final session: ≥ 9/10 per sign, 0 wrong accepts, 0 accepts on 50 negatives, < 2 s live | `docs/experiments/recognition.md` |
| **G3** On-device (Tue 27) | P3 parity run: same label (or "?") on every calibration clip, Mac vs simulator | spot-check the parity report | `docs/experiments/recognition.md` |
| **G4** Real call (Thu 29) | whole CI suite green on the commit that is installed | T2 full script live twice; recipient repeats each sentence exactly | `docs/experiments/device.md` |

## 3. What the E2E suite proves (and what it can't)

| Test (`tests/e2e/test_demo_script.py`) | Safety rule it guards |
|---|---|
| `test_plan_demo_script_end_to_end` | §1 turns 0–6: disclosure, captions, 3b wrong chip removed, exact text, goodbye |
| `test_nothing_is_spoken_before_send` | Nothing is spoken unless the user taps SEND |
| `test_double_send_speaks_once`, `test_duplicate_event_delivery_speaks_once` | Approval is single use (app side and Bolna side) |
| `test_stale_turn_approval_is_not_spoken` | A new turn wipes the old approval |
| `test_send_during_receptionist_speech_is_not_delivered_then_resent_once` | B24: no `spoken` → `not_delivered`; a dead turn never speaks later; re-SEND speaks once |
| `test_silence_gets_the_holding_line_and_no_caption` | `[silence]` gets the holding line and is not a caption |
| `test_end_while_reply_is_in_flight_is_not_spoken`, `test_approve_after_end_is_not_spoken` | Ended calls stay silent |
| `test_unknown_contact_is_refused_and_never_dialled`, `test_start_call_without_app_token_is_refused` | Only allowlisted, authenticated calls |

FakeBolna follows Bolna's docs, not observed behaviour. It can't prove B23 (graph agent
with a custom LLM), real latency, Deepgram transcripts or Sarvam audio. V4 does that.

## 4. Mutation testing for the safety rules

PLAN §8: every safety rule needs a test that fails if the rule is removed. Measure it
with [mutmut](https://github.com/boxed/mutmut) (no new dependency; run it ad hoc).

| Module | Rule | Target kill rate |
|---|---|---|
| `app/calls.py` | single-use approval, stale turn, ended call, allowlist, `not_delivered` | > 90% |
| `app/custom_llm.py` | speak only after `claim_reply`, `[silence]` → holding line, captions | > 90% |
| `app/validator.py`, `app/templates.py` | no invented day/time/number/name, chip meanings kept, 25-word cap | > 90% |
| `app/markers.py`, `app/contacts.py` | marker parsing, `contact_id=+E164` parsing | > 90% |

```sh
cd backend
uv run --with mutmut mutmut run                  # reads [tool.mutmut] below
uv run --with mutmut mutmut results              # survivors and kill counts
uv run --with mutmut mutmut show <mutant-name>   # the diff of one survivor
uv run --with mutmut mutmut browse               # interactive retest after fixing tests
```

Suggested `[tool.mutmut]` block when the team adopts it (add `mutants/` to `.gitignore`):

```toml
[tool.mutmut]
source_paths = ["app/"]
only_mutate = ["app/calls.py", "app/custom_llm.py", "app/validator.py", "app/templates.py", "app/markers.py", "app/contacts.py"]
also_copy = ["fakes/", "tests/"]
pytest_add_cli_args_test_selection = ["tests/"]
```

Each surviving mutant is either a missing test (write it) or an equivalent mutant (note
why in the PR). Run before G1 and after any change to a safety module. The E2E suite
was checked this way against a throwaway implementation: removing single-use claims,
stale-turn checks, the ended-call guard, the allowlist, the `[silence]` branch, caption
forwarding or the `spoken` confirmation each fails at least one test.

## 5. Day-by-day checklist

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
