# CallSession

The app's side of a call (PLAN.md §3, §4 and task A2): the wire messages, the backend
client and `TurnStore`, the one observable source of truth for a call. A standalone Swift
package with no dependencies. iOS 17+ and macOS 14+.

```
 SwiftUI views ──taps──▶ TurnStore ──AppMessage──▶ MessageOutbox ──▶ BackendClient ──▶ WebSocket
      ▲                     │  (rules live here)       (ordered,          (JSON, bearer      (pings
      └──── observes ───────┘                           drops on failure)  token)            every 20 s)
                            ▲
                            └──ServerMessage── BackendClient.events ◀── WebSocket
```

## Pieces

| File | What it does |
|---|---|
| `Vocabulary.swift` | The 34 signs the backend accepts (12 template signs + 22 ASL glosses), the rehearsed eight, the call purpose, the backend limits and `TurnID` |
| `Messages.swift` | `AppMessage` / `ServerMessage` mirroring `backend/app/protocol.py`. Unknown server types decode to `.unknown` |
| `WebSocketTransport.swift` | Transport protocol and `URLSessionWebSocketTransport` (Authorization on the upgrade request, receive loop as an `AsyncStream`, client ping every 20 s for Heroku) |
| `BackendClient.swift` | `BackendConfig` (base URL + `APP_TOKEN`, injected), `startCall`, `connect`, `send`, `events` |
| `MessageOutbox.swift` | Sends in tap order; drops queued messages after a failure, a disconnect or End |
| `TurnStore.swift` | Call state, captions, current turn, chips, draft and sending phase, with the safety rules |
| `LiveCall.swift` | Wires the client, outbox and store for one call; `onConnectionLost` tells the owner when the socket closes by itself so it can `connect()` again |

## Safety rules enforced by `TurnStore`

- Only recognised chips are sent; `?` chips never are, and nothing is sent when no recognised chip remains.
- A draft is shown only if it is for the current turn and recognised chips exist. Any chip change clears the old draft.
- SEND approves exactly the shown draft once (1–300 Unicode scalars, while the call is `in_call` or `speaking`), then a new turn starts with no chips or draft. While that reply is still being spoken, SEND waits; the screen shows STOP instead.
- STOP is sent at most once per reply, and only while a reply is being spoken.
- Clear wipes chips and draft on a new turn id, so a late draft for the old chips is stale. Nothing is sent.
- `spoken` marks the reply delivered and adds it to the transcript as the user's words.
- `not_delivered` offers re-SEND. Only an explicit `resend()` approves the same text again, on a new turn id.
- End drops anything queued, sends `end`, wipes chips, draft and any pending approval, and ignores later input and events. Captions stay as a read-only transcript.
- A lost socket (or a backend `error` status) shows "Nothing will be sent", wipes chips and draft (captions stay) and drops the queue. Nothing is resent after reconnecting; the store leaves `.error` when the backend sends a status.
- `LiveCall.connect()` reopens only after a plain drop. After close code 4401 (bad token), 4404 (unknown call) or 4409 (another socket took over) it does nothing; `lastClose` says which, for the UI.

## Use

```swift
let config = BackendConfig(baseURL: appConfig.backendURL, appToken: appConfig.appToken)
let call = try await LiveCall.start(
    client: BackendClient(config: config), contactID: "city_clinic", purpose: .doctorAppointment)
// Views observe call.store; buttons call add/remove/useQuickReply/send/resend/stop/end.
```

## Test

XCTest needs full Xcode (the Command Line Tools have no XCTest):

```sh
cd ios/Packages/CallSession
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer swift test
```

Without Xcode, `swift build` still compiles the library.
