# Evidence: iOS app ↔ real backend code, end to end (24 Oct 2026)

The first run of the iOS app against the real backend code (PR #27, task A2). **Executed**
on the development Mac, iPhone simulator (iOS 27.0), Xcode 27.1. Free: no Bolna, Groq or
Sarvam, nothing dialled. How to repeat it: [TESTING.md](../../../TESTING.md#app--local-backend-end-to-end).

```
iOS simulator app ──POST /calls, WebSocket──▶ local_demo backend (real create_app, CallManager,
(-IsharaDriver live,                           custom-LLM endpoint, template drafts)
 scripted recognizer)                                │ start_call, events   ▲ webhooks, custom-LLM POSTs
                                                     ▼                      │
                                                   ScriptedBolna: rings, answers, plays the receptionist
                                                   prints every line the agent "speaks"
```

| Step | Command |
|---|---|
| Server (as in `ios/README.md`; this run used port 8799) | `cd backend && uv run python -m scripts.local_demo --port 8799 --delay 0.3 > /tmp/local-demo.log` |
| App config | `ios/Ishara/Config/Secrets.xcconfig`: `ISHARA_BACKEND_URL = http:/$()/127.0.0.1:8799`, `ISHARA_APP_TOKEN = ishara-local-demo` (the local demo's public dev token) |
| Test | `TEST_RUNNER_ISHARA_LOCAL_BACKEND=1 TEST_RUNNER_ISHARA_LOCAL_BACKEND_LOG=/tmp/local-demo.log xcodebuild … -only-testing:IsharaUITests/LocalBackendCallUITests test` |

**Result:** `LocalBackendCallUITests/testClinicCallThroughTheLocalBackend` passed. The
test walks PLAN §1 and checks, from the server log, that nothing was spoken before each
SEND, that the removed `afternoon` chip and the `[?]` chip never reached the spoken text,
and that only the fixed disclosure and goodbye were said without a SEND.

What the stand-in Bolna "spoke" (each of the 3 calls in the log is identical, 7 lines per call):

```
agent says: Hello, I'm calling for a Deaf caller who is using Ishara, a sign-language app. Their replies may take a few seconds.
agent says: Hello, I'd like a doctor's appointment tomorrow.
receptionist says: We have 4 pm tomorrow. Does that work?
agent says: No, sorry, that doesn't work. Is there anything in the morning?
receptionist says: Yes, 10:30 tomorrow morning.
agent says: Yes, that works. Thank you.
agent says: Thank you for your time. Goodbye.
```

## Files

| File | What it shows |
|---|---|
| `e2e-1-draft.jpg` | Turn 1: chips hello · doctor · tomorrow → template draft "Hello, I'd like a doctor's appointment tomorrow.", SEND enabled |
| `e2e-2-caption.jpg` | After SEND: "✓ Delivered", the spoken line in the transcript, the receptionist's caption from the backend |
| `e2e-3-draft.jpg` | Turn 3: chips no · morning (wrong `afternoon` already removed) → template draft |
| `e2e-5-draft.jpg` | Turn 5: chips yes · ? · thankyou → draft "Yes, that works. Thank you." (the `?` is not in it) |
| `e2e-6-ended.jpg` | After End: "You ended the call" |
| `e2e-server-log.txt` | The local demo server's output for 3 calls: `agent says` / `receptionist says`, Bolna status moves and the custom-LLM request shapes (lengths and roles only). Copied verbatim; it holds no keys or phone numbers, only random local call ids and the public dev token |

## Limits

- The receptionist and Bolna are scripted (`ScriptedBolna`), drafts are templates, and
  chips come from the scripted recognizer, so this proves the app ↔ backend wiring, not
  recognition, Groq, real voice or Bolna's behaviour (that is V4/A3).
- Taken before PRs #37 and #38: the app did not yet show the agent's lines as captions,
  and the ended screen still wiped the transcript (review finding F1, since fixed; see
  [the verified fixes](../ios-fixes-verified-24oct/README.md)).
- The Xcode result bundle stays local (it holds machine paths); the screenshots are the
  test's own attachments, downscaled.
