# iOS capabilities and seamless conversation workflows for Ishara

## Can Ishara augment an ordinary cellular call rather than replace calling?

### Takeaway

**Hard requirement, clarified by user during research:** an ordinary cellular Phone call from the user's own number to the clinic; Ishara mediates that existing call. Bolna-originated calls, callbacks and a two-call relay are excluded. Apple publicly supports AAC speech injection into ordinary calls; system Live Captions may supply the user's return channel without Ishara obtaining call audio. The entire camera + injection + captions combination is **DOCS-ONLY, NOT EXECUTED**. Research evidence checked 2026-10-18; user reports iPhone 17, installed iOS version unknown.

### Cited Findings

- **Public supported mechanism:** Apple's AAC sample adds synthesized app speech to Phone, FaceTime and most VoIP apps using Apple voice processing, on iOS 18.2+. It requires the device-wide Add Audio in Calls setting, app permission and `NSMicrophoneInjectionUsageDescription`. `setPreferredMicrophoneInjectionMode(.spokenAudio)` enables injection; a notification reports availability. Apple's setup specifically tests an already-active call. [Apple AAC sample](https://developer.apple.com/documentation/avfaudio/adding-synthesized-speech-to-calls); [original Markdown verified](https://developer.apple.com/tutorials/data/documentation/avfaudio/adding-synthesized-speech-to-calls.md).
- **Important audio rule:** injection mixes spoken app audio with microphone audio. Muting the call's input also mutes injection. Do not design around the ordinary Phone mute button silencing room noise while preserving Ishara speech. [MicrophoneInjectionMode](https://developer.apple.com/documentation/avfaudio/avaudiosession/microphoneinjectionmode).
- **Focused audio recheck, 2026-10-18:** the current `spokenAudio` case explicitly describes injecting speech alongside microphone audio. Neither that case, its enum page nor the setter documentation promises ducking, muting or suppressing the room microphone while app speech plays. Possible route-specific processing must be measured; do not assert that room noise is automatically removed, or that no attenuation could ever occur. [Exact spokenAudio case](https://developer.apple.com/documentation/avfaudio/avaudiosession/microphoneinjectionmode/spokenaudio); [setter](https://developer.apple.com/documentation/avfaudio/avaudiosession/setpreferredmicrophoneinjectionmode(_:)).
- Apple supports opening another app during an ongoing Phone call, returning via the green call indicator. Hands-free audio destinations are available. This supports investigating normal Phone call followed by foreground Ishara. It does not certify camera coexistence. [While on a call](https://support.apple.com/guide/iphone/while-on-a-call-iph3c9951d7/ios).
- **OS restriction for app-owned processing:** Apple DTS explicitly says no supported API gives an unrelated app live audio from a call it does not carry. The engineer explains each calling app controls its own playback and recording streams. [Apple DTS, thread 841340](https://developer.apple.com/forums/thread/841340).
- **CallKit is not the transport:** the same DTS explanation distinguishes calling UI/system coordination from a media-carrying framework. Adding CallKit alone does not grant cellular audio, PSTN access or permission to use another caller's identity. [Apple DTS, thread 841340](https://developer.apple.com/forums/thread/841340).
- **Newer, relevant public API:** LiveCommunicationKit's default-dialer facilities initiate cellular conversations and can keep custom dialer UI visible. This is distinct from being the default VoIP calling app. Apple requires `com.apple.developer.dialing-app`; its guide states testing requires an EU-registered developer account and a device located in the EU. Context7 reports `startCellularConversation` availability iOS 26+. This restriction concerns Apple's developer-account/device eligibility, not merely the phone number's country. No received-audio permission is established by these APIs. [Apple default-dialer guide](https://developer.apple.com/documentation/livecommunicationkit/preparing-your-app-to-be-the-default-dialer-app); [entitlement](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.developer.dialing-app).

### Inferences

- **Product-oriented candidate:** user places/answers their usual carrier call, opens Ishara, props the phone, signs, and reads a system caption overlay. Ordinary cellular carriage should retain the user's usual carrier calling identity rather than an intermediary's outbound number; exact caller-ID presentation remains carrier/account-dependent and was not tested. This inference follows from continuing the existing call, not from a newly claimed caller-ID API.
- Remote-audio access being unavailable to Ishara **does not mean the user cannot receive captions**. The system can caption a call while refusing its audio to third-party apps. We should correct any blanket dismissal of native augmentation.
- Native AAC can emit resolved speech without an internet speech service. Bolna must fit this native-call requirement through an independently supported service (such as non-telephony speech generation, if documented), rather than changing how the user calls. Do not place Bolna in the diagram solely to claim usage; another researcher is checking standalone interfaces.
- A camera-only capture session should avoid Ishara competing to record the Phone call microphone. This is an engineering strategy, not proof of concurrent system behavior.
- **Minimum normal-call flow proposal:** (1) complete one-time AAC/camera/caption onboarding; (2) place or answer the usual call in Phone/Contacts; (3) open Ishara with one app/shortcut/available Live Activity tap; (4) keep Ishara foreground, set phone down and sign/read; (5) end with native Phone controls. Existing contacts and carrier identity remain the starting point. The OS may impose call confirmation or transition steps depending on launch path; no zero-action takeover is established.
- **Capture/session separation:** only video enters the recognition pipeline during a Phone call. Use the supported AAC speech path and inspect injection availability rather than start a competing `.playAndRecord` microphone pipeline or try to reconfigure Phone's audio. The exact audio-session category/options and synthesizer ownership must follow Apple's runnable sample and be validated with camera active; no guessed audio configuration is certified by these notes. For face-to-face, a separate session may legitimately own microphone input.
- **Start versus return:** a Live Activity can deep-link back to Ishara once appropriately started. It is not evidence of permission to automatically launch the app/camera or wake inference when any ordinary cellular call begins. An explicit Open Ishara step is the honest initial workflow; research a user-invoked shortcut separately if worth reducing navigation.
- **End-call ownership:** use the native Phone/system call controls to hang up the existing cellular call. Stopping Ishara capture or injected speech is a separate action and must not be labeled as ending the call. `CXCallObserver` permits observing system call changes; this grants no demonstrated cellular-call control. CallKit's `CXEndCallAction` documentation describes the provider/delegate action, and `TelephonyConversationManager` documents initiating cellular calls. Neither consulted reference establishes a general third-party right to terminate an unrelated existing Phone call. Therefore an in-Ishara cellular Hang Up button is unproven, not a promised API. [Call observation](https://developer.apple.com/documentation/callkit/cxcallobserver); [CallKit end action](https://developer.apple.com/documentation/callkit/cxendcallaction); [cellular manager](https://developer.apple.com/documentation/livecommunicationkit/telephonyconversationmanager).

### Gaps

- No physical iPhone experiment was performed, and no source found explicitly certifies camera + AAC injection + system Live Captions simultaneously. Need exact iOS version/build, carrier, call type and audio route.
- Unverified: end-to-end speech latency, audio routing, speaker feedback, whether injected utterances are themselves captioned, interruptions, call hold, AirPods/Bluetooth behavior, and camera continuity while opening Ishara after dialing.
- Native system captions would not give Ishara a supported live transcript feed. Context-dependent model decisions that require receptionist text cannot silently assume this feed exists. User copy/paste is available in some caption settings, but breaks the intended seamless flow.
- A normal phone call can continue with another app foreground, but one or more manual app transitions remain unless a permitted initiation mechanism proves otherwise. Do not promise a custom native dialer in India based on the EU-restricted API. User's developer-account region and actual device location were not verified.

## Could system Live Captions provide the return path, and which languages work?

### Takeaway

System captions are a credible **English demo candidate**, not a verified universal return path. The latest Apple availability page fetched is explicitly for **iOS/iPadOS 27** and includes English (India), while Hindi is absent. iPhone model alone does not prove the installed OS exposes that locale.

### Cited Findings

- Apple's guide says Live Captions supports iPhone 11 and newer, can transcribe iPhone/app audio or the surroundings, and offers a movable/full-screen caption window. Setup is Settings → Accessibility → Live Captions. It warns accuracy varies and is unsuitable for high-risk/emergency reliance. The current guide distinguishes one-minute call-caption retention (cleared when the call ends, no capture/copy) from one-hour retention (copy/screenshot/recording allowed, with an audible transcription announcement to call participants). [Apple Live Captions guide](https://support.apple.com/guide/iphone/get-live-captions-of-spoken-audio-iphe0990f7bb/ios).
- Current iOS 27 feature availability lists English (Australia, Canada, India, Singapore, UK, US), French (Canada/France), German, Japanese, Korean, Cantonese, Mandarin and Spanish locales. Hindi and Indian regional languages are absent from **Accessibility: Live Captions**. This is not the broader list for Name Recognition or general Apple Intelligence. [Apple iOS/iPadOS 27 availability](https://www.apple.com/in/ios/feature-availability/#accessibility-live-captions).
- FaceTime also has its own caption controls. Apple's current Live Translation list differs from the caption locale list; translation support cannot be inferred from caption support. [FaceTime captions/translation](https://support.apple.com/guide/iphone/use-live-captions-and-live-translation-iphb41156356/ios).
- **Transcription versus translation, focused recheck 2026-10-18:** English (India) Live Captions transcribes English speech; it does not establish Hindi-speech-to-English translation. Apple's current Phone Live Translation guide lists one-to-one calls in English (UK/US), French (France), German, Italian, Portuguese (Brazil), Spanish (Spain), Chinese (Simplified/Traditional), Japanese and Korean. Hindi is absent. The Phone Translate App's separate Hindi support is not evidence that Phone Live Translation supports Hindi. [Current Phone-specific translation guide](https://support.apple.com/guide/iphone/see-translations-during-phone-calls-ly3pl0v38sek/ios); [Apple feature availability](https://www.apple.com/in/ios/feature-availability/).
- Phone Live Translation requires Apple Intelligence enabled plus downloaded source/target languages. Apple says this feature family is available from iOS 26 onward; the currently served guide targets iOS 27. iPhone17 meets the stated hardware class (iPhone16 or later), but exact installed OS, assets, matching supported Siri/device language and regional eligibility still matter. Current Apple requirements describe China-mainland purchase/account/location restrictions and features varying by region; no India-specific exclusion was established for Phone translation. [Apple Intelligence requirements and feature footnotes](https://support.apple.com/en-us/121115).

### Inferences

- Native AAC + English captions can preserve ordinary calling more closely than forcing a new call provider. It needs honest onboarding rather than a promise of zero setup.
- If receptionist speech must be Hindi, a regional language, or mixed Hindi-English, native captions are not a documented complete solution. Since call rerouting is excluded and Ishara cannot read Phone audio, this is a real unresolved requirement boundary. Installing an ASR SDK does not supply inaccessible audio. Do not silently offer a cloud relay as an equivalent workaround; discuss the exact supported language scope with the user after checking the device.
- Minimum expected manual setup: enable Add Audio in Calls; grant Ishara injection/camera permissions; enable Live Captions, select supported language/input and choose retention/privacy preference; position overlay away from key controls. During each call, open/return to Ishara and make the signing space visible. Which settings persist and which controls reappear need testing.
- System caption timing and layout are outside Ishara's control. Reading while signing and finding the overlay could introduce attention shifts; treat this as an interaction cost to measure.
- Phone Live Translation's guide describes text/spoken translation inside the Phone app and manual start controls; it does not establish that its translated text floats above a different foreground app. Do not treat the movable Accessibility Live Captions window as the same UI or assume it receives translated rather than original call speech. Background continuation and translated-caption visibility with Ishara camera foreground are empirical gaps, even for a supported language pair.

### Gaps

- Inspect exact installed iOS, region and actual Live Captions language selection before recommending an OS update. Do not tell the user an update is necessary merely because the current web guide is iOS 27.
- Need tests with the specific receptionist accent and mixed-language utterances. Locale listing is availability evidence, not measured recognition accuracy.
- Need verify caption overlay remains usable above Ishara's camera, respects orientation, survives call state changes and does not expose unintended content in the recorded demo.
- Hindi-to-English translated captions are **not established by current Phone support**; this is a time-bound finding, not a claim that Apple can never add Hindi. Recheck actual device language options before making a final supported-language promise. No translation/caption app switching test was run.

## Can camera capture live in Dynamic Island, or continue during ordinary calling?

### Takeaway

Dynamic Island is a useful status/return surface, not an independently running camera-recognition engine. Foreground Ishara is the strongest initial camera arrangement. Public PiP/multitasking mechanisms exist, so saying all background iPhone camera use is impossible is outdated; eligibility and app purpose matter.

### Cited Findings

- ActivityKit supplies current state, quick App Intent actions and deep links. Live Activities run in a sandbox without their own network/location access; app updates or ActivityKit push notifications supply state. Combined static/dynamic data is limited to 4 KB. [ActivityKit guide](https://developer.apple.com/documentation/activitykit/displaying-live-data-with-live-activities).
- `isMultitaskingCameraAccessSupported` is true under documented conditions including apps linked against iOS 18+ using the `voip` background mode, an appropriate camera entitlement, or supported Stage Manager iPads. The enabled state must still be set and observed. [Current AVCaptureSession property](https://developer.apple.com/documentation/avfoundation/avcapturesession/ismultitaskingcameraaccesssupported).
- Apple's PiP video-call controller docs say camera use in PiP is available via `isMultitaskingCameraAccessEnabled` from iOS 16+, with an entitlement needed for earlier deployment targets. This is a documented mechanism for video calls, not blanket approval for any camera task. [Video-call PiP controller](https://developer.apple.com/documentation/avkit/avpictureinpicturevideocallviewcontroller).
- Generic camera background access can be interrupted; Apple documents the background interruption reason. This general rule must be read together with the more specific multitasking exceptions. [Background interruption](https://developer.apple.com/documentation/avfoundation/avcapturesession/interruptionreason/videodevicenotavailableinbackground).
- Apple DTS, July 2025, explicitly advises against enabling the VoIP background mode for a non-VoIP app. App Review 2.5.4 limits background services to intended purposes; 2.5.14 requires consent and an indication when recording user activity. Review 5.1.2(i) addresses disclosure/permission for sharing personal data with third parties, including AI. [DTS thread 791671](https://developer.apple.com/forums/thread/791671); [App Review guidelines](https://developer.apple.com/app-store/review/guidelines/).
- The system allows only one app to use the camera at a time and documents interruptions from another client or system pressure. Foreground/capture state and thermal pressure require recovery handling. [Camera multitasking guide](https://developer.apple.com/documentation/avkit/accessing-the-camera-while-multitasking-on-ipad).
- iPhone 17 has an 18 MP Center Stage front camera, autofocus and Center Stage video calling. These specifications do not prove that automatic cropping retains the full signing space or establish model inference performance. [Apple iPhone 17 specifications](https://www.apple.com/iphone-17/specs/).

### Inferences

- Proposed Live Activity content: call connected/disconnected, capture paused, recognition active/uncertain, and a return-to-Ishara control. Do not stream a camera feed or rely on Live Activity execution for inference. Whether simultaneous native Phone and Ishara activities receive useful prominence is untested.
- A true Ishara VoIP/video-relay implementation could evaluate supported PiP camera capture. A native-call AAC sidecar is not automatically a VoIP app just because Phone is active elsewhere. Do not add a fake VoIP declaration to obtain background time.
- FaceTime video and Ishara camera could contend for the same camera; audio-only native Phone call is a cleaner first experiment. FaceTime audio and third-party voice-processing calls require separate tests.
- Use controlled front-camera framing as the initial baseline. Evaluate auto-framing/zoom/portrait effects rather than assuming default face-oriented processing helps hands/body recognition. A fixed crop and orientation may be more stable for temporal inference.

### Gaps

- The exact supported entitlement path for an accessibility sidecar camera session outside a true video call was not established. Documentation language establishes conditional mechanisms; App Review approval is not proven by an API compiling.
- No camera-only session, foreground/background transition, PiP, Live Activity, thermal or on-device inference test was run.
- Need measure model-observation continuity when native call controls, permission prompts, screen lock and another camera app interrupt capture. Capture interruption must never be reported as continued listening/signing.

## What user workflow preserves ordinary communication while respecting signing?

### Takeaway

Prefer a conversation interface with minimal per-turn action, while retaining deliberate repair. A hands-free phone position follows the physical needs of signing, not a claim that Deaf users have validated Ishara. Captions are a chosen prototype return channel, not a substitute proven suitable for every ISL signer.

### Cited Findings

- W3C explains sign languages include hands, arms, facial expressions and body position, vary by region/language, and are many Deaf people's first language. Some people find written language/caption speed difficult. Its production guidance recommends clear lighting, contrast and complete signing space, often extending below the waist, above the head and to either side. This is general signing-video guidance, not empirical ISL classifier advice. [W3C sign languages](https://www.w3.org/WAI/media/av/sign-languages/).
- Deaf Connect's VRI guide advises positioning the camera to show face, body and arms, avoiding backlighting, and suggests landscape orientation for phones. Its specific Skype instructions are old; use the framing principle, not its obsolete software choice. [Deaf Connect VRI instructional guide, December 2022](https://deafconnect.org.au/wp-content/uploads/2022/12/221206_Deaf-Connect-VRI-Instructional-Guide.pdf).
- Deaf Connect recommends speaking directly to the Deaf person, allowing interpretation time, rephrasing when necessary and not confusing interpreter delay with inactivity. These are human interpretation principles, not measured timing requirements for Ishara. [Deaf Connect communication guidance](https://deafconnect.org.au/wp-content/uploads/2023/02/Communication-Tips.pdf).
- Existing Indian alternatives matter: ISLRTC announced VRS integration into national helpline 14456 on 2025-02-01. SignAble describes human ISL VRI/VRS supporting everyday conversations on phones and other devices. These establish existing service approaches, not verified present availability, quality or an automatically replaceable human role. Do not reuse SignAble's unsourced population/interpreter counts. [Indian government announcement](https://www.pib.gov.in/PressReleseDetailm.aspx?PRID=2098822); [SignAble service description](https://signable.live/).

### Inferences

- **Working state proposal, not a frozen design:** `Ready → Connecting → Listening/Reading ↔ Signing → Resolving → Speaking → Listening/Reading → Ended`. Add explicit `Needs repair`, `Capture interrupted`, `Connection lost`, and `Unsupported request` states. Recognition state is independent of whose turn it is: an incoming utterance may arrive while the user is signing.
- **Before call:** choose contact as usual; set only context the bounded demo truly needs. One-time permissions/framing setup should be separate from every-turn interaction. A stand/propped phone permits two hands and face visibility. Test landscape versus portrait and caption legibility at the needed distance rather than mandate an invented universal posture.
- **During call:** show readable remote captions plus a small honest capture/interpretation indicator; speak a completed high-confidence utterance automatically. A brief uncertainty pause may trigger extra verification. If unresolved, offer candidate correction or re-sign. Do not require an ordinary Send action every turn. Never turn likely conversational intent into accepted times or personal facts without the user's actual input.
- **Repair:** preserve the original remote utterance where available, show uncertainty, allow deliberate repeat/re-sign/candidate choice, and communicate a short waiting phrase only when appropriate. A small nod or smile during conversation must not automatically become agreement; deliberate affirmative gesture boundaries need evidence.
- **Face-to-face:** foreground camera captures signer, local speech output reaches the hearing person, microphone/ASR captions their response. This has no cross-app call-audio barrier, but still requires echo suppression/segmentation, readable framing and bounded vocabulary. It should share conversation/repair concepts without being used to avoid the call-first objective.
- **No Deaf participant:** call the persona provisional, state which team member performs the demonstration, and distinguish system success from usability or Deaf-community acceptance. Public resources inform assumptions; they do not validate this particular interaction.

### Gaps

- No Deaf-user interviews or usability research were performed. Reading language/fluency, regional ISL variation, device posture, desired correction technique, privacy preference and accessibility requirements remain assumptions.
- Unknown how appointment dialogue handles names, dates, numbers, alternative times, interruptions, repetition, silence, unsupported requests and call failure. The vocabulary must follow this workflow plus actual model/dataset coverage.
- No evidence yet that the proposed 25 signs plus two head gestures supports all required appointment turns. Recognition of isolated labels is not proof of grammatical sentence reconstruction.

## Can a future face-to-face mode offer direct Hindi/English captions locally?

### Takeaway

Face-to-face mode can own microphone audio and therefore use Apple or external ASR directly. This is fundamentally different from native Phone augmentation, which does not expose the remote call stream. SpeechAnalyzer is a credible on-device path, but Hindi offline support must be checked on the real device rather than inferred from general language lists.

### Cited Findings

- Apple introduced SpeechAnalyzer in iOS 26 to analyze supplied audio buffers/streams. Its SpeechTranscriber model runs on device, supports conversational/long-form use cases and needs downloadable assets; DictationTranscriber offers an alternate model/device/language coverage. Downloading assets is an initial network operation, not evidence that ongoing recognition uploads audio. [Apple WWDC25 SpeechAnalyzer session](https://developer.apple.com/videos/play/wwdc2025/277/).
- SpeechTranscriber exposes separate supported/downloadable and installed locale lists. Its supported list is empty on an unsupported device. Neither this API page nor the fetched guide hardcodes an authoritative current Hindi locale list; inspect the actual runtime lists and download requirements. [Supported locales](https://developer.apple.com/documentation/speech/speechtranscriber/supportedlocales); [installed locales](https://developer.apple.com/documentation/speech/speechtranscriber/installedlocales); [DictationTranscriber locales](https://developer.apple.com/documentation/speech/dictationtranscriber/supportedlocales).
- SpeechAnalyzer accepts the app's own buffers or microphone-capture inputs, produces asynchronous results, and exposes resource/error/lifecycle controls. It does not claim privileged access to other apps' audio. [SpeechAnalyzer](https://developer.apple.com/documentation/speech/speechanalyzer).
- The older SFSpeechRecognizer reports `supportsOnDeviceRecognition`; a request can require on-device processing only if support is true, otherwise recognition requires a network. Locale support and offline capability are distinct checks. [On-device support](https://developer.apple.com/documentation/speech/sfspeechrecognizer/supportsondevicerecognition); [request restriction](https://developer.apple.com/documentation/speech/sfspeechrecognitionrequest/requiresondevicerecognition).

### Inferences

- **Future mode path:** local microphone → supported speech module → in-app captions; camera → sign recognition/interpretation → local speech playback. The app can then use the in-app transcript for decisions, unlike the native Phone/system-caption path. Camera and microphone permission, routing, echo suppression and speaker feedback still need engineering and tests.
- Check `en-IN` and `hi-IN` against SpeechTranscriber, then DictationTranscriber, and where needed SFSpeechRecognizer's locale/device capability. A framework supporting Hindi somewhere is not proof of offline Hindi on this iPhone. Mixed-language accuracy is a separate experiment.
- Pause/suppress self-generated speech in the recognition input or use appropriate echo handling so the app does not repeatedly caption or react to its own output. Do not route Phone speaker output through an invented second microphone stream as a workaround for the call-audio restriction.

### Gaps

- No runtime locale/device query or model asset installation performed. English/Hindi local transcription latency, accuracy, code-switching and echo behavior remain untested.
- No assertion that SpeechTranscriber itself supports Hindi is warranted by these consulted sources. A failure to support it would constrain the module choice, not make all face-to-face Hindi captions impossible.

## Which native-call path should be tested, and what evidence would settle the architecture?

### Takeaway

Native Phone augmentation is the required architecture direction. Determine which supported system pieces can compose into that experience. Bolna must serve this direction through non-telephony capabilities, if any, rather than originate or bridge the call. No path is verified end to end.

### Cited Findings

| Claim ledger (evidence date 2026-10-18) | Classification | Evidence and limit |
|---|---|---|
| App speech can enter Phone calls | Public supported mechanism; docs verified | [Apple AAC sample](https://developer.apple.com/documentation/avfaudio/adding-synthesized-speech-to-calls); no Ishara runtime test |
| Opening Ishara need not end the Phone call | Public supported workflow; docs verified | [Phone user guide](https://support.apple.com/guide/iphone/while-on-a-call-iph3c9951d7/ios); camera/audio combination unknown |
| Ishara can read unrelated cellular call audio | Contradicted by platform evidence | [Apple DTS](https://developer.apple.com/forums/thread/841340); no supported public API |
| System captions can show iPhone audio without exposing it to Ishara | Public supported user feature plus inference about combined workflow | [Live Captions guide](https://support.apple.com/guide/iphone/get-live-captions-of-spoken-audio-iphe0990f7bb/ios); overlay + camera not tested |
| Hindi captions exist on current Apple list | Not supported by consulted list | [iOS27 availability](https://www.apple.com/in/ios/feature-availability/#accessibility-live-captions); English India is listed; installed iOS unknown |
| Background camera is always impossible on iPhone | Overbroad/outdated | [Multitasking-camera API](https://developer.apple.com/documentation/avfoundation/avcapturesession/ismultitaskingcameraaccesssupported); conditional mechanism |
| A Live Activity alone keeps recognition running | Unsupported | [ActivityKit](https://developer.apple.com/documentation/activitykit/displaying-live-data-with-live-activities); UI/state surface, not capture service |
| Every app can become native cellular dialer worldwide | Contradicted by scope restriction | [Default-dialer guide](https://developer.apple.com/documentation/livecommunicationkit/preparing-your-app-to-be-the-default-dialer-app); EU test eligibility |
| Adding CallKit grants PSTN/media/caller ID | Contradicted | [Apple DTS](https://developer.apple.com/forums/thread/841340); own media transport still required |
| Muting native microphone preserves synthesized speech injection | Contradicted | [Injection mode](https://developer.apple.com/documentation/avfaudio/avaudiosession/microphoneinjectionmode); both muted |
| AAC automatically suppresses room microphone during speech | Not promised by consulted documentation | [Exact spokenAudio case](https://developer.apple.com/documentation/avfaudio/avaudiosession/microphoneinjectionmode/spokenaudio); actual mixing/attenuation needs measurement |
| English(India) captions mean Hindi speech is translated to English | Unsupported conflation | [Phone translation guide](https://support.apple.com/guide/iphone/see-translations-during-phone-calls-ly3pl0v38sek/ios); current Hindi pair not listed |
| Phone translated captions remain visible above Ishara | Missing runtime evidence | [Phone translation guide](https://support.apple.com/guide/iphone/see-translations-during-phone-calls-ly3pl0v38sek/ios); described in-app UI, no floating translation guarantee |
| An Ishara Stop button ends the unrelated cellular call | Not established; do not promise | [Call observer](https://developer.apple.com/documentation/callkit/cxcallobserver); native system hangup remains planned control |
| Front-camera hardware proves adequate live ISL accuracy | Missing empirical evidence | [iPhone17 specs](https://www.apple.com/iphone-17/specs/) establish hardware only |
| Human ISL relay services already exist in India | Source-verified availability claims, not service tested | [ISLRTC/PIB](https://www.pib.gov.in/PressReleseDetailm.aspx?PRID=2098822); [SignAble](https://signable.live/) |

### Inferences

| Candidate | Workflow/benefit | Engineering required | Gate before selection |
|---|---|---|---|
| Normal Phone + foreground Ishara AAC + system captions | Closest to existing cellular call; hearing party needs no app; ordinary carrier call retained | Camera inference, utterance boundaries, AAC session management, setup/recovery; no automatic receptionist-text feed | Actual iPhone17/iOS: camera + injection + English caption overlay; silence/interruptions; language requirement |
| Native Phone + Ishara + externally generated speech, if supported | Keeps existing carrier call; fetched synthesized audio could be played through Apple's AAC mechanism | Secure text-to-audio request, supported audio playback/session handling, cancellation/deduplication; no third-party access to Phone audio | Provider has documented standalone speech API; complete fetched-utterance injection works; latency/cancellation are acceptable |
| Face-to-face foreground | Same phone mediates in-person conversation; no PSTN dependency | Local camera/TTS and ASR, speaker echo/turn handling, orientation/readability | Face/body/hands framing, ASR/TTS interference, correction burden |

- The external-speech row is a candidate, **not a claim that Bolna exposes that interface**. Another researcher covers it. A Bolna verified outbound number is not needed for the native Phone/AAC path. A future device experiment needs a consenting recipient and the user's working carrier call; no outbound call has been made.
- Native path should be tested promptly after permissions are understood, rather than discarded merely because third-party call recording is unavailable. Earlier service-originated/callback proposals are superseded by the user's requirement.
- Prefer recognition, interpretation and speech-output boundaries that keep the ordinary Phone call intact. System captions remain a parallel user-facing channel rather than an assumed transcript input to the decision model. This is a design hypothesis, not implementation authorization.
- Candidate success measures: wrong automatically spoken utterances; repeated signs/taps per conversation; time from completed sign to audible output; caption delay; turn loss; complete booking with confirmed details; visible recovery after camera/network interruptions. No numeric acceptance targets can be claimed as user-validated yet.

### Gaps

1. Record exact iPhone17 iOS version/build, locale/languages, account/device eligibility, available setup settings, test audio route and carrier.
2. In a separately authorized physical-device spike, first test synthesized fixed speech during an existing native call; add camera-only preview; then add system captions; then sustained signing/inference. Record which addition introduces failure. This is a future experiment proposal, not an executed test or request to write code now.
3. Test native call microphone mute, speaker/earpiece/Bluetooth, caption handling of injected speech, remote interruption, app switch, lock/unlock and camera interruption. Distinguish unsupported states visibly.
4. Verify Bolna non-telephony services independently. If none fits, report that constraint honestly; do not replace the native call with a service-originated call. Research exact competition requirements before claiming an integration satisfies them.
5. Evaluate actual vocabulary and full appointment turn coverage. Keep high-stakes/emergency use outside claims supported by these tests.
6. Separate distribution decisions: a local signed Xcode demonstration, TestFlight and App Store review are different release stages. Public API availability does not guarantee App Review approval, and a local demo does not establish entitlement eligibility.

Research method: Context7 resolve-library-id selected `/websites/developer_apple_avfaudio` and `/websites/developer_apple_de`; queries covered AAC, camera multitasking and LiveCommunicationKit. Exa search/fetch verified original Apple Markdown, support pages, W3C, Deaf Connect and Indian government/provider sources. No metered Exa research agent, installations, product code, calls or paid services were used. Search snippets were followed with original documents for central claims. All behavior remains DOCS-ONLY unless the note explicitly states otherwise; none was executed.
