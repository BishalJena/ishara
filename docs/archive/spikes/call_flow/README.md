# Minimal call-flow feasibility spike

Throwaway diagnostics, not the product app. The same Ishara signing workspace is the
target for ordinary Phone and WhatsApp **voice** calls. Test WhatsApp first; a pass
there does not establish carrier-call compatibility. No calls are originated here.

## What has actually run

- Bolna account and voice-catalog GET requests: **200**.
- One synthetic speech request to the historical `/user/tts_sample` route: **403**
  after approximately 715 ms. No speech audio was returned. This measures the failed
  request, not speech latency. The reason for denial and endpoint eligibility are
  unresolved; a valid key alone has not established hosted synthesis access.
- Offline flow and credential/audio validation tests: **13 passed** initially.
- Xcode unsigned generic-iOS build: **passed**. The only reported warning was
  skipped App Intents metadata extraction because the sample has no App Intents.
- Signed development build: **passed** with the existing local Apple development
  identity. Signing/team details are not saved in the project. Physical installation
  is pending the user's USB connection, trust and device readiness.
- No actual call, sign recognition, camera coexistence or live caption test has run.
  The user cannot connect their iPhone yet and currently has only a Bolna key.

## Offline mock

```sh
python3 spikes/call_flow/flow_mock.py
python3 -m unittest discover -s spikes/call_flow -p 'test_*.py'
```

Synthetic sign IDs resolve to fixed phrases, simulated audio completion is followed
by synthetic partial/final captions, and cancellation rejects a late result. Tests
also cover unknown signs, provider failure, duplicate completion and disconnection.
Phone and WhatsApp are **scenario labels**, not platform adapters. The mock emits
no audio and invokes neither Bolna nor Apple. It verifies our proposed lifecycle
logic only. Cancelling real playback cannot retract words someone already heard.

## Real Bolna probe

```sh
python3 spikes/call_flow/bolna_probe.py check
python3 spikes/call_flow/bolna_probe.py speech --phrase initial
```

The speech command makes a real provider request; do not confuse it with the mock.
Only three non-telephony routes are allowed. Keys stay on the Mac, API error bodies
are withheld, redirects are blocked, and generated evidence/audio stays under the
ignored `artifacts/` directory. A failed speech attempt removes its previous clip.
The sample endpoint is a historical candidate under investigation, not a promised
production integration. Bolna OSS with separate provider credentials remains an
unexecuted alternative. No full Bolna pipeline has been installed or validated.

## WhatsApp device check, when available

Open `ios/AddSynthesizedSpeechToCalls.xcodeproj` in Xcode, choose your own development
team and your iPhone, and run. The project contains Apple's licensed AAC sample,
adapted to fixed test buttons, immediate Stop and external audio-file playback.
It now also includes a front-camera preview with no microphone capture, recording
or recognition, so camera/audio/caption coexistence can be tested on the device.
It contains no API key and does not place a call. Signing/provisioning and physical
installation remain necessary; an unsigned local build is not an installable app.

1. In iPhone Settings, enable Accessibility → Audio & Visual → Add Audio in Calls.
2. Open the diagnostic app, then place a WhatsApp **voice** call yourself to a
   consenting person. Return to the diagnostic and enable **Add Audio To Call**;
   grant the system permission when prompted.
3. Tap **Speak test sentence**. Have the recipient repeat what they actually heard.
   This is an **Apple voice control test**, not Bolna speech.
4. Tap Stop while speaking, wait through a signing-length pause, then try the second
   sentence. Note duplicates, dropped audio, route changes and call interruptions.
5. Enable system Live Captions, select **iPhone Audio**, and have the recipient say
   a different sentence. Check readable captions while the diagnostic is foreground.
6. Test an external Bolna clip separately once genuine audio generation works. Local
   Apple speech succeeding does not prove external clip injection or Bolna works.
7. Repeat on a carrier Phone call later. Camera + captions + injected speech must
   then be tested concurrently using the **Front camera preview** toggle. Confirm
   the image keeps moving while speech plays and captions appear. The preview
   stops when the app goes to the background; background recognition is not tested.

Record exact iOS and WhatsApp versions, caption language, audio route, recipient
observations and failures locally. Do not commit phone numbers or call recordings.
Phone microphone mute also mutes injected speech. A local sound or an injection
availability indicator alone is not proof of delivery to the other person.

## Sources

- [Apple AAC sample and supported call mechanism](https://developer.apple.com/documentation/avfaudio/adding-synthesized-speech-to-calls)
- [Apple sample archive](https://docs-assets.developer.apple.com/published/77a3397c5287/AddingSynthesizedSpeechToCalls.zip); its license is retained in `ios/LICENSE.txt`.
- [Apple Live Captions](https://support.apple.com/guide/iphone/get-live-captions-of-spoken-audio-iphe0990f7bb/ios)
- [Historical Bolna speech-sample documentation](https://docs.bolna.ai/api-reference/voice/generate_tts): discovered in an index; current documentation redirect returned 404. Runtime returned 403, not evidence that this account can use it.
