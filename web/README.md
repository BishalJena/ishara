# Ishara web call desk

A phone-shaped browser companion matching the current native steer screens.
Live calls pursue the user’s own goal across services, using supplied context and
delivered live replies; the scripted clinic is only a rehearsal example.
The Python backend serves the web app, calls and ASL inference. It opens directly in
Scripted demo, which makes no telephone request. Choose Live call (or Settings
on a phone) and unlock with the backend's `APP_TOKEN` for live calling and signing.
The code is exchanged for an eight-hour HttpOnly session cookie; it is never
embedded in JavaScript or saved in local storage.

## Use it

Open the configured backend HTTPS root in a current browser. Start in
Scripted demo, write a request, and follow the captions and editable reply preview.
For a real call, choose Live call and a consenting, allowlisted recipient. The
Bolna trial also requires that number to be verified in its dashboard. Real calls
consume credits and originate from Ishara's Bolna number. Avoid reloading or
closing the tab during a live call.

Tap the hand button to open signing, then Enable camera. Keep your face, shoulders and hands in view; record
one sign, finish, and review the word chips before choosing Use these words.
Supported words: hello, thank you, yes, no, now, please, tomorrow, wait. Candidate
words require explicit confirmation; uncertain footage adds nothing. The words
are added to the editable request or reply, never automatically spoken.

This is experimental isolated-sign ASL recognition, not continuous translation.
It uses the same published model, full 250-way ranking and provisional cutoffs
as iOS. Browser/signer accuracy still needs rehearsal. Video stays in the browser;
MediaPipe extracts landmarks in a worker, and only coordinates go to the backend.
Coordinates are processed in memory and not retained. Recent call notes are saved
in this browser; use Clear beside Recent to remove them. Locking live calling hides
notes but does not erase them. The backend also keeps a private recovery copy of
completed notes for 24 hours after the last update; authenticated history can
restore these after a service restart.

Completed calls and saved calls lead with the automatic summary, followed by the
outcome, follow-ups and transcript. If the provider summary is late or missing,
the screen labels the recorded details clearly and keeps the transcript available.
Refresh call notes retrieves the existing backend record without redialing or
requesting another AI summary; refreshed notes are saved back to browser history.

## Development

From `web/`:

```sh
npm ci
npm run build
npm test
npm run test:browser
```

Build copies the existing ignored Holistic task from `ios/Ishara/LocalAssets/`
and SDK WASM assets, and writes `backend/web_static/`. Models and generated assets
are ignored by Git. Provision the iOS local models first (see its LocalAssets
README); never upload project history or private recordings to host this app.

For an integrated, entirely fake telephone server:

```sh
cd backend
uv run --extra web-recognition python -m scripts.web_demo
```

Open `http://127.0.0.1:8780`; its test-only access code is `ishara-web-demo`.
Even its Live call mode uses the scripted fake telephone service and templates.
The local demo runner does not read production credentials. `npm run dev` also
proxies API and WebSocket requests to that server.

## Production

Build the frontend, deploy `backend/app`, `backend/recognition` and
`backend/web_static`, and install dependencies with:

```sh
uv sync --locked --no-default-groups --extra web-recognition
```

Set `WEB_ASL_MODEL_PATH` to the unchanged `asl-signs.tflite` model outside the
release directory. Its SHA-256 must match `recognition/asl-bundle.json`. Serve
one uvicorn worker on the existing HTTPS address; same-origin cookies authenticate
both API requests and WebSockets. No CORS or browser bearer token is needed.
Do not restart the backend during a call.

Verification covers state transitions, stale proposal rejection, origin and
cookie protection, the complete fake call flow, mobile layout, and actual
MediaPipe initialization with uncertain fake-camera footage, including a stalled
video-playback regression after resizing. It does not establish
real telephone audio delivery, signer accuracy, or Deaf participant validation.

Settings shows backend reachability and offers a fresh check. An unavailable check
can be a network problem; it does not establish the server's power state. Hosting
accounts, production URLs and operator-specific tooling are configured separately
and are not part of this repository.
