# Ishara consolidated claim ledger

This is the dated **source claim ledger**. Executed ML results, timing and semantic
regressions are consolidated in the [experiment record](experiments/recognition.md).
Use the [handoff](HANDOFF.md) and [active plan](../PLAN.md) for current direction.
On **23 October 2026** the team chose Option C (a disclosed Bolna-placed call first,
the own-number call as a bonus); rows below that assumed the own-number call was the
only acceptable path are marked as superseded.

Evidence originally checked **18 October 2026**; rows marked *(23 Oct)* were checked on 23 October. All actual account observations are redacted below; no keys, account identifiers, telephone values or raw responses are recorded.

## Status legend

| Status | Meaning |
|---|---|
| VERIFIED | A specifically stated source/metadata fact was inspected, or a specifically stated read-only observation was executed. Each row identifies which; this never implies end-to-end runtime validation. |
| DOCS-ONLY | A current source documents behavior or an interface, but no relevant device/model/session experiment was executed here. |
| REPORTED | An author's numerical experiment or benchmark, not reproduced here; hardware/data/protocol boundaries apply. |
| UNVERIFIED | Inherited result lacking reviewed artifacts, engineering hypothesis, or missing empirical/metadata evidence. |
| CONTRADICTED | A precise older assertion conflicts with current primary evidence or the controlling user requirement. The correction is stated explicitly. |

## Product, platform and workflow

| ID | Claim | Status | Exact source and evidence limits |
|---|---|---|---|
| W01 | The call must remain the user's ordinary own-number cellular Phone call; service-originated/callback/second-call designs do not satisfy it. | CONTRADICTED — superseded by user decision *(23 Oct)* | Was the user's requirement on 18 Oct. On 23 Oct the user chose Option C: a disclosed Bolna-placed call (Path B) first, own-number call (Path A) as a bonus. See [PLAN.md](../PLAN.md#2-decisions). |
| W02 | Target device is iPhone 17; installed iOS is unknown. | VERIFIED — user report / UNVERIFIED OS | User reply in this thread. [Hardware specifications](https://www.apple.com/iphone-17/specs/) establish camera hardware, not installed software or recognition performance. |
| A01 | Apple supports synthesized app speech entering existing calls on iOS 18.2+ with settings and permission. | DOCS-ONLY | [AAC sample](https://developer.apple.com/documentation/avfaudio/adding-synthesized-speech-to-calls); device-wide Add Audio in Calls, app permission/usage description, availability handling; Phone/FaceTime/compatible voice-processing VoIP. No execution. |
| A02 | Injection mixes app speech with microphone input; native call mute also mutes injection. | DOCS-ONLY | [Microphone injection mode](https://developer.apple.com/documentation/avfaudio/avaudiosession/microphoneinjectionmode). No route or mute experiment. |
| A03 | AAC automatically ducks/suppresses the room microphone during app speech. | UNVERIFIED — not promised | [spokenAudio](https://developer.apple.com/documentation/avfaudio/avaudiosession/microphoneinjectionmode/spokenaudio), [setter](https://developer.apple.com/documentation/avfaudio/avaudiosession/setpreferredmicrophoneinjectionmode(_:)). Consulted docs describe mixing; actual attenuation/routing requires measurement. |
| A04 | A Phone call can continue while another app is foreground. | DOCS-ONLY | [Apple Phone guide](https://support.apple.com/guide/iphone/while-on-a-call-iph3c9951d7/ios). Does not prove simultaneous camera/AAC/captions. |
| A05 | Ishara can obtain unrelated live cellular-call audio through a supported public API. | CONTRADICTED | [Apple DTS](https://developer.apple.com/forums/thread/841340): each calling app owns its streams; no supported unrelated-call audio API. CallKit does not grant media transport. |
| A06 | System caption visibility means Ishara has a transcript and can extract receptionist intent. | CONTRADICTED — unsupported inference | [Live Captions](https://support.apple.com/guide/iphone/get-live-captions-of-spoken-audio-iphe0990f7bb/ios), [audio boundary](https://developer.apple.com/forums/thread/841340). No app-readable caption feed established. User reading is not model observation. |
| A07 | Default cellular dialer functionality is generally available for any demo region. | CONTRADICTED | [Dialer guide](https://developer.apple.com/documentation/livecommunicationkit/preparing-your-app-to-be-the-default-dialer-app), [entitlement](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.developer.dialing-app). Documented testing requires EU account/device eligibility; not a blanket India route or media permission. |
| A08 | Ishara can end the unrelated existing Phone call with its own Stop button. | UNVERIFIED — not established | [Call observer](https://developer.apple.com/documentation/callkit/cxcallobserver), [end action](https://developer.apple.com/documentation/callkit/cxendcallaction), [cellular manager](https://developer.apple.com/documentation/livecommunicationkit/telephonyconversationmanager). Observation/provider actions do not establish general unrelated-call hangup. Keep native hangup. |
| A09 | Live Captions can display iPhone audio in a movable window on supported iPhones. | DOCS-ONLY | [User guide](https://support.apple.com/guide/iphone/get-live-captions-of-spoken-audio-iphe0990f7bb/ios); iPhone 11+, locale/region/OS conditions. Retention modes differ, including call announcement/copy behavior. Camera-overlay composition not tested. |
| A10 | Current Apple availability lists English (India), but not Hindi, for Live Captions. | VERIFIED — source list only | [iOS/iPadOS 27 list](https://www.apple.com/in/ios/feature-availability/#accessibility-live-captions). This page targets iOS 27, not proof of installed OS/options. |
| A11 | English (India) captions imply Hindi-speech-to-English translation. | CONTRADICTED | [Phone Live Translation](https://support.apple.com/guide/iphone/see-translations-during-phone-calls-ly3pl0v38sek/ios), [feature list](https://www.apple.com/in/ios/feature-availability/). Transcription and translation differ; current Phone list does not include Hindi. |
| A12 | Phone translated captions are available above foreground Ishara. | UNVERIFIED | [Phone guide](https://support.apple.com/guide/iphone/see-translations-during-phone-calls-ly3pl0v38sek/ios) describes Phone UI and manual controls, not floating translated-text delivery over another app. |
| A13 | Phone Live Translation eligibility follows from iPhone 17 alone. | CONTRADICTED | [Apple Intelligence requirements](https://support.apple.com/en-us/121115): software, language/assets, region/account and enablement still apply. No device check performed. |
| A14 | A Live Activity independently runs the signing camera/inference. | CONTRADICTED — interface scope | [ActivityKit](https://developer.apple.com/documentation/activitykit/displaying-live-data-with-live-activities): state/UI surface with no own network/location access, 4 KB combined data. Return/status candidate only. |
| A20 | Apple's call injection carries any app audio (e.g. a TTS clip played with AVAudioPlayer), not only AVSpeechSynthesizer output. | DOCS-ONLY *(23 Oct)* | [AAC sample](https://developer.apple.com/documentation/avfaudio/adding-synthesized-speech-to-calls): setting text "Any audio from apps, along with microphone input, will be audible during a call"; "the system plays the app's audio locally and adds it to the microphone's input stream." Not run on a device. |
| A15 | All background camera access is impossible on iPhone. | CONTRADICTED — overbroad | [Camera multitasking](https://developer.apple.com/documentation/avfoundation/avcapturesession/ismultitaskingcameraaccesssupported), [video-call PiP](https://developer.apple.com/documentation/avkit/avpictureinpicturevideocallviewcontroller). Conditional mechanisms exist; sidecar eligibility/approval is not established. |
| A16 | A non-VoIP sidecar can declare VoIP background mode just to retain camera execution. | CONTRADICTED — inappropriate assumption | [DTS](https://developer.apple.com/forums/thread/791671), [review guidelines](https://developer.apple.com/app-store/review/guidelines/). Do not infer review approval from API availability. |
| A17 | Foreground camera-only capture, AAC and system captions work together on this iPhone. | UNVERIFIED — engineering hypothesis | [AAC sample](https://developer.apple.com/documentation/avfaudio/adding-synthesized-speech-to-calls), [caption guide](https://support.apple.com/guide/iphone/get-live-captions-of-spoken-audio-iphe0990f7bb/ios), [capture interruptions](https://developer.apple.com/documentation/avfoundation/avcapturesession/interruptionreason/videodevicenotavailableinbackground). Combined device experiment not executed. |
| A18 | SpeechAnalyzer can analyze app-supplied audio on device; exact Hindi support must be queried. | DOCS-ONLY | [WWDC25](https://developer.apple.com/videos/play/wwdc2025/277/), [SpeechAnalyzer](https://developer.apple.com/documentation/speech/speechanalyzer), [SpeechTranscriber locales](https://developer.apple.com/documentation/speech/speechtranscriber/supportedlocales). Relevant to future face-to-face mode; no access to unrelated Phone audio. |
| A19 | A locale listing automatically establishes offline ASR on this device. | CONTRADICTED | [Installed locales](https://developer.apple.com/documentation/speech/speechtranscriber/installedlocales), [DictationTranscriber](https://developer.apple.com/documentation/speech/dictationtranscriber/supportedlocales), [on-device support](https://developer.apple.com/documentation/speech/sfspeechrecognizer/supportsondevicerecognition), [request restriction](https://developer.apple.com/documentation/speech/sfspeechrecognitionrequest/requiresondevicerecognition). Assets, device and on-device capability must be checked. |
| W03 | Full signing space and caption language preferences affect the interaction. | VERIFIED — published guidance; persona UNVERIFIED | [W3C](https://www.w3.org/WAI/media/av/sign-languages/), [Deaf Connect framing](https://deafconnect.org.au/wp-content/uploads/2022/12/221206_Deaf-Connect-VRI-Instructional-Guide.pdf). General guidance, not Ishara usability validation; no Deaf participant. |
| W04 | Human ISL relay service approaches already exist in India. | VERIFIED — source claims, service not tested | [Government VRS announcement](https://www.pib.gov.in/PressReleseDetailm.aspx?PRID=2098822), [SignAble](https://signable.live/). Present service quality/availability and unsourced prevalence numbers not verified. |

## Recognition, data and decision models

| ID | Claim | Status | Exact source and evidence limits |
|---|---|---|---|
| R01 | The inherited baseline is 62% top-1 / 83% top-3 on 26 words. | UNVERIFIED — inherited | User-supplied brief/updates; no reviewed artifact, split, script or confusion matrix. Not a live-phone result or final-vocabulary score. |
| R02 | Historical inventory arithmetic gives 25 classifier labels plus two proposed head inputs. | VERIFIED — arithmetic only | Inventory in [recognition note](archive/2026-10-18-recognition-notes.md); 26 − 5 + 4 = 25. Data coverage, utility, gesture semantics and deliberate consent remain unverified. |
| R03 | INCLUDE has 263 isolated classes; original paper 4,287 videos, archive 4,292 after five additions. | VERIFIED — source metadata | [Paper](https://dl.acm.org/doi/10.1145/3394171.3413528), [archive](https://zenodo.org/records/4010759). Original/current counts differ for an explained reason; not independent validation examples. |
| R04 | INCLUDE is CC-BY-4.0; repository code licensing is separate. | VERIFIED — metadata | [Machine-readable data terms](https://zenodo.org/api/records/4010759), [code repository](https://github.com/AI4Bharat/INCLUDE). MIT code does not change data terms. |
| R05 | A Hugging Face INCLUDE-derived copy has 5,250 entries, proving more independent validated samples. | UNVERIFIED — unsupported inference | [Mirror](https://huggingface.co/datasets/ai4bharat/INCLUDE) card/search surfaced 5,250 rows, but no manifest was audited. Unique-video count, extra independent source clips, signer diversity and validation are unverified; use original archive manifests. |
| R06 | CISLR covers roughly 4,700 words and has non-commercial dataset terms. | VERIFIED — source facts | [Author repository](https://github.com/Exploration-Lab/CISLR), [paper](https://aclanthology.org/2022.emnlp-main.707/). Dataset README CC-BY-NC-4.0 controls data; MIT repository badge is code metadata. |
| R07 | iSign reports 118,228 video–text pairs and multiple video/pose/text tasks. | VERIFIED — published resource description | [Paper](https://aclanthology.org/2024.findings-acl.643/), [project](https://exploration-lab.github.io/iSign/). Segmentation/transcription noise and small validation sample do not establish full corpus quality. |
| R08 | iSign public README specifies CC-BY-NC-SA-4.0 plus research/non-commercial/no-further-redistribution conditions. | VERIFIED — retrieved dataset-card statements only | [Public README](https://huggingface.co/datasets/Exploration-Lab/iSign/blob/main/README.md), [dataset card](https://huggingface.co/datasets/Exploration-Lab/iSign). Gated video access was not obtained. Reconcile the license/access/redistribution wording before reuse; this row records source statements, not a legal interpretation. Source-video splits do not establish signer independence. |
| R09 | Phrase/sentence ISL data does not exist. | CONTRADICTED | [ISLTranslate](https://aclanthology.org/2023.findings-acl.665/), [iSign](https://exploration-lab.github.io/iSign/), [ISL-CSLTR](https://doi.org/10.17632/kcmpdxky7p). Exact appointment coverage/terms remain unaudited. |
| R10 | ISL-CSLTR describes 700 videos, 100 sentences and seven signers. | VERIFIED — published description only | [Original record](https://doi.org/10.17632/kcmpdxky7p). Contributor breakdown in abstract does not transparently reconcile; inspect original metadata before demographic claims. |
| R11 | Continuous fingerspelling research solves arbitrary names/numbers. | CONTRADICTED — benchmark interpretation | [2025 paper](https://aclanthology.org/2025.wslp-main.6/) reports 82.91% character error rate, not accuracy; 1,308 segments/499 source videos/70.85 minutes. REPORTED, not rerun. |
| R12 | Temporal specialist scores demonstrate strong original-split performance but weaker generalization. | REPORTED | [2026 study](https://openaccess.thecvf.com/content/CVPR2026W/MSLR/papers/Varanasi_Isolated_Sign_Language_Recognition_via_MediaPipe_Landmarks_A_Case_Study_CVPRW_2026_paper.pdf): 95.88% INCLUDE original / 83.82% approximate pseudo-signer / 19.20% CISLR. No reproduced test or verified real signer-independent split. |
| R13 | Generic zero-shot visual models are already established ISL recognizers. | CONTRADICTED — overclaim | [Specialist study](https://openaccess.thecvf.com/content/CVPR2026W/MSLR/papers/Varanasi_Isolated_Sign_Language_Recognition_via_MediaPipe_Landmarks_A_Case_Study_CVPRW_2026_paper.pdf): tested zero-shot VLMs near zero; fine-tuned LLaVA-NeXT 32.24%. Those comparisons do not test Jev. |
| R14 | MediaPipe hand landmarks are sign-language labels. | CONTRADICTED | [iOS guide](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/ios), [model description](https://developers.google.com/edge/mediapipe/solutions/vision/gesture_recognizer/index). Geometry/gesture outputs require separate temporal/language modeling; default max hands is one. |
| R15 | ISLRTC dictionary media has blanket commercial reuse permission. | CONTRADICTED | [FAQ Q23](https://islrtc.nic.in/faq/) allows research/teaching/ISL technology development with no resale/profiteering and acknowledgment. Regional variation and non-one-to-one English mappings matter. Host identity is not a license for unrelated clips. |
| R16 | Public INCLUDE videos exist for all 12 demo signs. | CONTRADICTED — partial *(23 Oct)* | [INCLUDE label map](https://raw.githubusercontent.com/AI4Bharat/INCLUDE/master/label_maps/label_map_include.json) (263 labels) covers hello, thankyou, doctor, hospital, today, tomorrow, morning, afternoon, evening, time, good and weekdays; not yes, no, sorry, please, wait, name or appointment. Use ISLRTC dictionary media for learning those (see R15 terms). Re-checked 23 Oct: `thankyou` is present and its INCLUDE clips are already in the local corpus. |
| M01 | Jev is text-only. | CONTRADICTED — stale indexed description | [Live image guide](https://docs.typesafe.ai/images) supersedes [indexed model page](https://github.com/typesafe-docs/typesafeai/blob/main/docs/12-models.md) returned via Context7. Images need experimental header and assets; PNG/JPEG frame history is not native video streaming. |
| M02 | Jev 1.13/1.14 support images; latest/preview aliases map to 1.13/1.14 as checked. | DOCS-ONLY / VERIFIED mapping | [Images](https://docs.typesafe.ai/images), [models](https://docs.typesafe.ai/models). Box requires 1.14. Pin actual version; no inference/ISL test was made. |
| M03 | Jev confidence is a measured probability of correct ISL recognition. | CONTRADICTED | [Confidence](https://docs.typesafe.ai/confidence): Choice transformation of largest option probability relative to uniform. Domain thresholds/calibration need experiments. |
| M04 | Laya supplies text/structured-state bounded decisions, not a demonstrated visual ISL pipeline. | DOCS-ONLY | [Upstream](https://github.com/nandhakishorm/laya), [model card](https://huggingface.co/convaiinnovations/laya). Apache-2.0 code/weights; checkpoint language behavior and overconfidence need evaluation. |
| M05 | Laya MLX short-question timings establish iPhone performance. | CONTRADICTED — hardware mismatch | [MLX port](https://github.com/mizorewww/laya-mlx): REPORTED 13.42 ms p50 English/7.39 ms multilingual on M3 Max 40-GPU-core/128 GiB, excluding model load; Python/macOS. Not mobile end-to-end latency. |
| M06 | No Laya iPhone path exists. | CONTRADICTED | [laya-ANE](https://github.com/vipuldivyanshu92/laya-ANE), [iOS instructions](https://raw.githubusercontent.com/vipuldivyanshu92/laya-ANE/main/ios/README.md) provide SwiftUI/Core ML candidate, iOS17+, 421M default, 160-token capacity. Local model prep/signing needed; dummy bundles are untrained. No iPhone17 validation. |
| M07 | Other Core ML and Swift ports establish identical device coverage/parity. | UNVERIFIED — implementations differ | [FluidInference conversion](https://huggingface.co/FluidInference/laya-coreml) reports M5 Pro/macOS measurements, ~614 MB FP16/~448–453 MB int8-embedding buckets; aggressive quantization parity failures. [Swift MLX port](https://github.com/MstyAI/laya-mlx-swift) explicitly macOS14+, not iOS proof. |
| M08 | LayaKit packaging/platform matrix was independently inspected. | UNVERIFIED — unavailable | [Registry pointer](https://systemonemodels.org/examples/tools/layakit/); direct repository/raw fetches failed. Registry mention alone is not source inspection. |
| M09 | Google SL2T multilingual training means a public ISL API/iPhone product exists. | CONTRADICTED — conflated claims | [Announcement](https://deepmind.google/blog/putting-sign-language-ai-into-users-hands/): 100k+ hours/50+ sign languages training; initial ASL→English Pixel11 Gboard/Live Transcribe deployment. No public ISL API/weights/iPhone path established. |
| M10 | SignGemma is an available public ISL engine. | UNVERIFIED — not established | [Access thread](https://discuss.ai.google.dev/t/how-to-get-access-to-signgemma/106766), [release thread](https://discuss.ai.google.dev/t/signgemma-release-date/113794): official no-access/no-specific-timeline statements; later community questions do not constitute release. |
| M11 | Whole-phrase recognition, buffered boundaries and candidate verification can meet this workflow. | UNVERIFIED — engineering hypothesis | [Phrase tasks](https://exploration-lab.github.io/iSign/), [Jev images](https://docs.typesafe.ai/images). Exact coverage, naturalness, false accepts, sustained latency and repair burden remain untested. No new phrase is validated by hearing reenactment. |

## Bolna and competition

| ID | Claim | Status | Exact source and evidence limits |
|---|---|---|---|
| B01 | Bolna key authenticates and exposes voice catalogs. | VERIFIED — executed read-only | Exactly `GET /user/me` and English/Hindi `GET /api/v1/voice-config/tts` returned HTTP200; concurrency max2/current0; both catalogs 16 provider/29 model entries. [Limits semantics](https://www.bolna.ai/docs/api-reference/limits.md), [catalog reference](https://www.bolna.ai/docs/api-reference/voice/get_providers). No balance value/raw response retained; no synthesis/credit sufficiency proved. |
| B02 | Bolna Custom TTS `/audio/speech` is a Bolna standalone synthesis endpoint for Ishara. | CONTRADICTED | [Custom TTS](https://www.bolna.ai/docs/custom-tts.md): developer supplies endpoint; Bolna calls upstream and expects whole MP3 within 20s. This is not `api.bolna.ai/audio/speech`. |
| B03 | A publicly documented standalone Bolna arbitrary-text synthesis API was found. | UNVERIFIED — bounded not-found | [Index](https://www.bolna.ai/docs/llms.txt), [TTS](https://www.bolna.ai/docs/text-to-speech.md), [voices](https://www.bolna.ai/docs/api-reference/voice/overview), [developer resources](https://www.bolna.ai/docs/developer-resources/overview.md), SDK/custom/event pages. These checked pages did not establish it; not proof no private/beta service exists. |
| B04 | Voice catalogs prove audio generation or language quality. | CONTRADICTED | [Voice APIs](https://www.bolna.ai/docs/api-reference/voice/overview). GET catalog metadata is not inference. Same en/hi counts do not mean all entries support either language. |
| B05 | Web Call v3 creates browser-agent WebRTC sessions with microphone access. | DOCS-ONLY | [Guide](https://www.bolna.ai/docs/developer-resources/sdks/web-call.md), [reference](https://www.bolna.ai/docs/developer-resources/sdks/web-call-api.md). Enablement on request; ~120s single-use setup credentials, 30s setup timeout are not connected lifetime guarantees. |
| B06 | SDK has documented sendText, live transcript or raw audio output callbacks. | UNVERIFIED — absent from inspected reference | [SDK reference](https://www.bolna.ai/docs/developer-resources/sdks/web-call-api.md). Listed states/permission/start/end/error/volume and start/stop/mute/state/run-ID do not establish those interfaces; private/beta methods remain possible. |
| B07 | Bolna WebRTC output can already be injected into an existing Phone call. | UNVERIFIED — engineering hypothesis | [SDK](https://www.bolna.ai/docs/developer-resources/sdks/web-call-api.md), [AAC](https://developer.apple.com/documentation/avfaudio/adding-synthesized-speech-to-calls). Need receive-only/mic/session behavior, exact text trigger, audio extraction/routing and lifetime proof. No session created. |
| B08 | Custom LLM supplies agent speech via developer upstream Chat Completions streaming. | DOCS-ONLY | [Contract](https://www.bolna.ai/docs/customizations/using-custom-llm.md). Public authenticated endpoint, OpenAI delta stream/[DONE], extra-body/control-task constraints. Not Responses API, not standalone Bolna inference, not unrelated Phone audio access. |
| B09 | A successful event publication guarantees exact speech delivery. | CONTRADICTED | [Events](https://www.bolna.ai/docs/graph-agent/event-injection.md): 202 publication; queued during generation/audio; proactive generation skipped if recipient speaking; unmatched event merges properties without speech. Runtime delivery/cancellation/repeated-node behavior untested. |
| B10 | Static cached-node speed applies to arbitrary newly recognized sentences. | CONTRADICTED | [Static nodes](https://www.bolna.ai/docs/graph-agent/static-nodes.md): audio rendered when agent saved; approximate cache speed is vendor claim, not dynamic TTS latency. |
| B11 | Status webhooks establish streaming partial captions. | CONTRADICTED | [Webhooks](https://www.bolna.ai/docs/post-call/polling-call-status-webhooks.md), [lifecycle](https://www.bolna.ai/docs/concepts/call-flow.md). Completed payload carries final transcript; status update is not partial-ASR contract. Applies to Bolna-owned session only. |
| B12 | Existing native Phone calling needs a Bolna-verified test number. | CONTRADICTED — wrong path | [Trial restrictions](https://www.bolna.ai/docs/pricing/outbound-calling-concurrency.md) concern Bolna outbound calling. User's required call uses existing carrier service; consenting device-test recipient is a different need. |
| B13 | Bolna POST /call preserves the user's ordinary SIM call automatically. | CONTRADICTED — wrong ownership | [Call API](https://www.bolna.ai/docs/api-reference/calls/make.md), [outbound](https://www.bolna.ai/docs/outbound/making-calls.md). Service/account numbers and destination govern it. Service-originated route is excluded regardless of UI resemblance. |
| B14 | Bolna has no SIP support. | CONTRADICTED — stale FAQ | [Current SIP guide](https://www.bolna.ai/docs/sip-trunking/overview.md) contradicts [FAQ](https://www.bolna.ai/docs/frequently-asked-questions.md). SIP does not make ordinary SIM calls controllable and is not the required workflow. |
| B15 | Agent default timers allow arbitrary signing pauses without inspection. | CONTRADICTED — defaults differ | [V2 schema](https://www.bolna.ai/docs/api-reference/agent/v2/get.md): hangup silence10s, total90s, online check true/10s; [engine guide](https://www.bolna.ai/docs/agent-setup/engine-tab.md). Actual saved config/maxima/keepalive behavior untested; only relevant if a non-PSTN agent session is selected. |
| B16 | Free LLM/static caching makes a Bolna call free. | CONTRADICTED | [Cost overview](https://www.bolna.ai/docs/get-started/what-it-costs.md), [pricing](https://www.bolna.ai/docs/pricing/call-pricing.md). Voice, telephony, platform/provider charges differ; no reliable all-in quote for account. No billable action executed. |
| B17 | Bolna session content can involve stored transcripts/recordings and US processing. | DOCS-ONLY | [Security](https://www.bolna.ai/docs/concepts/security.md). India residency is separate setup; webhook source-IP verification documented, HMAC not established. No actual session content processed. |
| B18 | A graph agent can be driven to speak by an external event during a live call, with event properties substituted into the node prompt. | DOCS-ONLY *(23 Oct)* | [Event injection](https://www.bolna.ai/docs/graph-agent/event-injection.md): `POST /v1/call/{run_id}/events`, properties merge into `context_data` and `{{variable}}` prompts; ~800 ms to speech on an LLM node (vendor figure). Combining this with a custom LLM that echoes the approved text verbatim is untested (plan task V4). |
| B19 | Bolna exposes a documented way to interrupt an utterance that is already playing. | UNVERIFIED — not found *(23 Oct)* | Event docs state events never interrupt active speech; the stop-call API covers queued/scheduled calls only ([stop call](https://www.bolna.ai/docs/api-reference/calls/stop_call.md)). STOP in Path B may only cancel unspoken replies. |
| B20 | Outbound test calls need a purchased, KYC-verified Indian number. | CONTRADICTED *(23 Oct)* | [Make call](https://www.bolna.ai/docs/api-reference/calls/make.md) / [API quickstart](https://www.bolna.ai/docs/quickstarts/api.md): omit `from_phone_number` to use the account default number. [Buying numbers](https://www.bolna.ai/docs/buying-phone-numbers.md): purchasing an Indian number needs KYC. |
| B21 | Sarvam, ElevenLabs, Cartesia voices and Deepgram nova ASR are inside Bolna's flat per-minute rate. | DOCS-ONLY *(23 Oct)* | [Preferred models](https://www.bolna.ai/docs/pricing/preferred-models.md): $0.06/min (₹5.52) flat rate including Sarvam bulbul v2/v3/v4-flash, ElevenLabs flash/turbo, Cartesia sonic, Deepgram nova-2/3; Kalpa/Smallest not listed. Telephony and platform fees extra. Snapshot; dashboard list governs. |
| B22 | Default silence settings suit a callee who waits while the user signs. | CONTRADICTED *(23 Oct)* | [Engine tab](https://www.bolna.ai/docs/agent-setup/engine-tab.md): hangup on user silence and user-online detection would fire while the receptionist waits; turn both off. [Static nodes](https://www.bolna.ai/docs/graph-agent/static-nodes.md): `repeat_after_silence_seconds` can play a holding line instead. |
| B23 | A graph agent can use a custom (OpenAI-compatible) LLM endpoint as its response LLM. | UNVERIFIED — not documented *(23 Oct)* | [Custom LLM](https://www.bolna.ai/docs/customizations/using-custom-llm.md) shows only `simple_llm_agent`; [graph agent setup](https://www.bolna.ai/docs/graph-agent/settings.md) lists OpenAI, Anthropic and Google as providers and does not mention custom endpoints. Path B depends on this; confirm at plan task V2/V3 before anything else. |
| B24 | An event that arrives while the callee is speaking still produces proactive speech. | CONTRADICTED *(23 Oct)* | [Event injection](https://www.bolna.ai/docs/graph-agent/event-injection.md): "If the user is mid-utterance when the event lands, the node transitions but the agent does not speak proactively." A SEND during receptionist speech may transition without speaking; the backend must detect a missing `spoken` and surface it. |
| B25 | The callee cannot cut off an approved sentence. | CONTRADICTED — defaults *(23 Oct)* | [Engine tab](https://www.bolna.ai/docs/agent-setup/engine-tab.md): speech above the interruption word count stops the agent, and the stopwords "Stop", "Wait", "Hold on" always pause it. [Graph settings](https://www.bolna.ai/docs/graph-agent/settings.md): a node can override "words to interrupt" to 0. [Static nodes](https://www.bolna.ai/docs/graph-agent/static-nodes.md): an LLM-node silence repeat sends `[silence]` in the history, which the custom LLM can use to tell a holding-line request from a transcript. |
| H01 | Submission is 31 Oct2026; ideas with a voice component qualify. | VERIFIED — official page | [Buildathon](https://www.bolna.ai/symphony/buildathon/): shortlist Nov3, interviews Nov5–7, results Nov8, finale Nov20 Bengaluru; top3 travel/top10 tickets. Not independent organizer confirmation beyond retrieved page. |
| H02 | Bolna integration is mandatory under the buildathon rules. | CONTRADICTED *(23 Oct)* | [Official page](https://www.bolna.ai/symphony/buildathon/): "Build whatever you like, as long as voice is part of it." Sponsors listed: Plivo, Exotel, Sarvam, Cartesia, Deepgram, Kalpa Labs. The team chose Bolna anyway. Exact deadline time/timezone, assets and rubric remain unestablished. |
| H03 | Heroku Eco dynos stay awake for a live custom-LLM endpoint. | CONTRADICTED *(23 Oct)* | [Heroku app sleeping](https://www.heroku.com/blog/app_sleeping_on_heroku/): Eco web dynos sleep after 30 min without traffic. [Request timeout](https://devcenter.heroku.com/articles/request-timeout): 30 s to respond; [WebSockets](https://devcenter.heroku.com/articles/websockets): idle connections need pings. Use Basic+ dynos. |
| H04 | Cerebras inference is free without setup. | CONTRADICTED — qualified *(23 Oct)* | [Change log](https://inference-docs.cerebras.ai/support/change-log): new accounts get $5 credit after adding a verified payment method; free tier has lower limits ([rate limits](https://inference-docs.cerebras.ai/support/rate-limits)). [Models](https://inference-docs.cerebras.ai/models/overview): `gpt-oss-120b` ~3000 tok/s, `qwen-3.8-27b` ~1850 tok/s (vendor figures). |

## Complete checked-source inventory

The inventory below retains every external URL linked in the three topic notes and the synthesis artifacts. It is an audit trail, not a claim that every source is equally authoritative or every runtime assertion has been exercised. Exact duplicate URLs are listed once; `.md`/HTML variants remain separate. Secondary articles and registry pointers are identified as such in their notes. Gated/unavailable items and source conflicts are recorded explicitly after the inventory.

**101 unique external URLs** are retained below.

| Source ID | Exact checked URL | Reference context |
|---|---|---|
| S001 | [paper](https://aclanthology.org/2022.emnlp-main.707/) | CLAIM-LEDGER.md, recognition-and-models.md |
| S002 | [ISLTranslate](https://aclanthology.org/2023.findings-acl.665/) | CLAIM-LEDGER.md, Ishara feasibility research.md, recognition-and-models.md |
| S003 | [Paper](https://aclanthology.org/2024.findings-acl.643/) | CLAIM-LEDGER.md, recognition-and-models.md |
| S004 | [2025 paper](https://aclanthology.org/2025.wslp-main.6/) | CLAIM-LEDGER.md, recognition-and-models.md |
| S005 | [Supplied article](https://aiidelist.com/blog/what-is-laya-mlx) | recognition-and-models.md |
| S006 | [Deaf Connect framing](https://deafconnect.org.au/wp-content/uploads/2022/12/221206_Deaf-Connect-VRI-Instructional-Guide.pdf) | CLAIM-LEDGER.md, Ishara feasibility research.md, ios-and-workflow.md |
| S007 | [Deaf Connect communication guidance](https://deafconnect.org.au/wp-content/uploads/2023/02/Communication-Tips.pdf) | ios-and-workflow.md |
| S008 | [Announcement](https://deepmind.google/blog/putting-sign-language-ai-into-users-hands/) | CLAIM-LEDGER.md, Ishara feasibility research.md, recognition-and-models.md |
| S009 | [review guidelines](https://developer.apple.com/app-store/review/guidelines/) | CLAIM-LEDGER.md, ios-and-workflow.md |
| S010 | [ActivityKit](https://developer.apple.com/documentation/activitykit/displaying-live-data-with-live-activities) | CLAIM-LEDGER.md, Ishara feasibility research.md, ios-and-workflow.md |
| S011 | [AAC sample](https://developer.apple.com/documentation/avfaudio/adding-synthesized-speech-to-calls) | CLAIM-LEDGER.md, Ishara feasibility research.md, ios-and-workflow.md |
| S012 | [Microphone injection mode](https://developer.apple.com/documentation/avfaudio/avaudiosession/microphoneinjectionmode) | CLAIM-LEDGER.md, Ishara feasibility research.md, ios-and-workflow.md |
| S013 | [spokenAudio](https://developer.apple.com/documentation/avfaudio/avaudiosession/microphoneinjectionmode/spokenaudio) | CLAIM-LEDGER.md, Ishara feasibility research.md, ios-and-workflow.md |
| S014 | [setter](https://developer.apple.com/documentation/avfaudio/avaudiosession/setpreferredmicrophoneinjectionmode(_:)) | CLAIM-LEDGER.md, ios-and-workflow.md |
| S015 | [capture interruptions](https://developer.apple.com/documentation/avfoundation/avcapturesession/interruptionreason/videodevicenotavailableinbackground) | CLAIM-LEDGER.md, ios-and-workflow.md |
| S016 | [Camera multitasking](https://developer.apple.com/documentation/avfoundation/avcapturesession/ismultitaskingcameraaccesssupported) | CLAIM-LEDGER.md, Ishara feasibility research.md, ios-and-workflow.md |
| S017 | [Camera multitasking guide](https://developer.apple.com/documentation/avkit/accessing-the-camera-while-multitasking-on-ipad) | ios-and-workflow.md |
| S018 | [video-call PiP](https://developer.apple.com/documentation/avkit/avpictureinpicturevideocallviewcontroller) | CLAIM-LEDGER.md, ios-and-workflow.md |
| S019 | [entitlement](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.developer.dialing-app) | CLAIM-LEDGER.md, ios-and-workflow.md |
| S020 | [Call observer](https://developer.apple.com/documentation/callkit/cxcallobserver) | CLAIM-LEDGER.md, Ishara feasibility research.md, ios-and-workflow.md |
| S021 | [end action](https://developer.apple.com/documentation/callkit/cxendcallaction) | CLAIM-LEDGER.md, ios-and-workflow.md |
| S022 | [Dialer guide](https://developer.apple.com/documentation/livecommunicationkit/preparing-your-app-to-be-the-default-dialer-app) | CLAIM-LEDGER.md, Ishara feasibility research.md, ios-and-workflow.md |
| S023 | [cellular manager](https://developer.apple.com/documentation/livecommunicationkit/telephonyconversationmanager) | CLAIM-LEDGER.md, Ishara feasibility research.md, ios-and-workflow.md |
| S024 | [DictationTranscriber](https://developer.apple.com/documentation/speech/dictationtranscriber/supportedlocales) | CLAIM-LEDGER.md, ios-and-workflow.md |
| S025 | [request restriction](https://developer.apple.com/documentation/speech/sfspeechrecognitionrequest/requiresondevicerecognition) | CLAIM-LEDGER.md, ios-and-workflow.md |
| S026 | [on-device support](https://developer.apple.com/documentation/speech/sfspeechrecognizer/supportsondevicerecognition) | CLAIM-LEDGER.md, ios-and-workflow.md |
| S027 | [SpeechAnalyzer](https://developer.apple.com/documentation/speech/speechanalyzer) | CLAIM-LEDGER.md, ios-and-workflow.md |
| S028 | [Installed locales](https://developer.apple.com/documentation/speech/speechtranscriber/installedlocales) | CLAIM-LEDGER.md, ios-and-workflow.md |
| S029 | [SpeechTranscriber locales](https://developer.apple.com/documentation/speech/speechtranscriber/supportedlocales) | CLAIM-LEDGER.md, ios-and-workflow.md |
| S030 | [DTS](https://developer.apple.com/forums/thread/791671) | CLAIM-LEDGER.md, Ishara feasibility research.md, ios-and-workflow.md |
| S031 | [Apple DTS](https://developer.apple.com/forums/thread/841340) | CLAIM-LEDGER.md, Ishara feasibility research.md, ios-and-workflow.md |
| S032 | [original Markdown verified](https://developer.apple.com/tutorials/data/documentation/avfaudio/adding-synthesized-speech-to-calls.md) | ios-and-workflow.md |
| S033 | [WWDC25](https://developer.apple.com/videos/play/wwdc2025/277/) | CLAIM-LEDGER.md, ios-and-workflow.md |
| S034 | [model description](https://developers.google.com/edge/mediapipe/solutions/vision/gesture_recognizer/index) | CLAIM-LEDGER.md, recognition-and-models.md |
| S035 | [iOS guide](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/ios) | CLAIM-LEDGER.md, Ishara feasibility research.md, recognition-and-models.md |
| S036 | [Access thread](https://discuss.ai.google.dev/t/how-to-get-access-to-signgemma/106766) | CLAIM-LEDGER.md, recognition-and-models.md |
| S037 | [release thread](https://discuss.ai.google.dev/t/signgemma-release-date/113794) | CLAIM-LEDGER.md, recognition-and-models.md |
| S038 | [Paper](https://dl.acm.org/doi/10.1145/3394171.3413528) | CLAIM-LEDGER.md, Ishara feasibility research.md, recognition-and-models.md |
| S039 | [Confidence](https://docs.typesafe.ai/confidence) | CLAIM-LEDGER.md, Ishara feasibility research.md, recognition-and-models.md |
| S040 | [Live image guide](https://docs.typesafe.ai/images) | CLAIM-LEDGER.md, Ishara feasibility research.md, recognition-and-models.md |
| S041 | [models](https://docs.typesafe.ai/models) | CLAIM-LEDGER.md, Ishara feasibility research.md, recognition-and-models.md |
| S042 | [ISL-CSLTR](https://doi.org/10.17632/kcmpdxky7p) | CLAIM-LEDGER.md, recognition-and-models.md |
| S043 | [project](https://exploration-lab.github.io/iSign/) | CLAIM-LEDGER.md, recognition-and-models.md |
| S044 | [code repository](https://github.com/AI4Bharat/INCLUDE) | CLAIM-LEDGER.md, recognition-and-models.md |
| S045 | [Author repository](https://github.com/Exploration-Lab/CISLR) | CLAIM-LEDGER.md, Ishara feasibility research.md, recognition-and-models.md |
| S046 | [Swift MLX port](https://github.com/MstyAI/laya-mlx-swift) | CLAIM-LEDGER.md, recognition-and-models.md |
| S047 | [MLX port](https://github.com/mizorewww/laya-mlx) | CLAIM-LEDGER.md, Ishara feasibility research.md, recognition-and-models.md |
| S048 | [Upstream](https://github.com/nandhakishorm/laya) | CLAIM-LEDGER.md, recognition-and-models.md |
| S049 | [indexed model page](https://github.com/typesafe-docs/typesafeai/blob/main/docs/12-models.md) | CLAIM-LEDGER.md, recognition-and-models.md |
| S050 | [laya-ANE](https://github.com/vipuldivyanshu92/laya-ANE) | CLAIM-LEDGER.md, Ishara feasibility research.md, recognition-and-models.md |
| S051 | [FluidInference conversion](https://huggingface.co/FluidInference/laya-coreml) | CLAIM-LEDGER.md, Ishara feasibility research.md, recognition-and-models.md |
| S052 | [model card](https://huggingface.co/convaiinnovations/laya) | CLAIM-LEDGER.md, recognition-and-models.md |
| S053 | [dataset card](https://huggingface.co/datasets/Exploration-Lab/iSign) | CLAIM-LEDGER.md, recognition-and-models.md |
| S054 | [Public README](https://huggingface.co/datasets/Exploration-Lab/iSign/blob/main/README.md) | CLAIM-LEDGER.md, Ishara feasibility research.md, recognition-and-models.md |
| S055 | [Mirror](https://huggingface.co/datasets/ai4bharat/INCLUDE) | CLAIM-LEDGER.md, recognition-and-models.md |
| S056 | [FAQ Q23](https://islrtc.nic.in/faq/) | CLAIM-LEDGER.md, Ishara feasibility research.md, recognition-and-models.md |
| S057 | [2026 study](https://openaccess.thecvf.com/content/CVPR2026W/MSLR/papers/Varanasi_Isolated_Sign_Language_Recognition_via_MediaPipe_Landmarks_A_Case_Study_CVPRW_2026_paper.pdf) | CLAIM-LEDGER.md, Ishara feasibility research.md, recognition-and-models.md |
| S058 | [iOS instructions](https://raw.githubusercontent.com/vipuldivyanshu92/laya-ANE/main/ios/README.md) | CLAIM-LEDGER.md, recognition-and-models.md |
| S059 | [SignAble](https://signable.live/) | CLAIM-LEDGER.md, Ishara feasibility research.md, ios-and-workflow.md |
| S060 | [Apple Intelligence requirements](https://support.apple.com/en-us/121115) | CLAIM-LEDGER.md, Ishara feasibility research.md, ios-and-workflow.md |
| S061 | [Live Captions](https://support.apple.com/guide/iphone/get-live-captions-of-spoken-audio-iphe0990f7bb/ios) | CLAIM-LEDGER.md, Ishara feasibility research.md, ios-and-workflow.md |
| S062 | [Phone Live Translation](https://support.apple.com/guide/iphone/see-translations-during-phone-calls-ly3pl0v38sek/ios) | CLAIM-LEDGER.md, Ishara feasibility research.md, ios-and-workflow.md |
| S063 | [FaceTime captions/translation](https://support.apple.com/guide/iphone/use-live-captions-and-live-translation-iphb41156356/ios) | ios-and-workflow.md |
| S064 | [Apple Phone guide](https://support.apple.com/guide/iphone/while-on-a-call-iph3c9951d7/ios) | CLAIM-LEDGER.md, Ishara feasibility research.md, ios-and-workflow.md |
| S065 | [Registry pointer](https://systemonemodels.org/examples/tools/layakit/) | CLAIM-LEDGER.md, recognition-and-models.md |
| S066 | [feature list](https://www.apple.com/in/ios/feature-availability/) | CLAIM-LEDGER.md, ios-and-workflow.md |
| S067 | [iOS/iPadOS 27 list](https://www.apple.com/in/ios/feature-availability/#accessibility-live-captions) | CLAIM-LEDGER.md, Ishara feasibility research.md, ios-and-workflow.md |
| S068 | [Hardware specifications](https://www.apple.com/iphone-17/specs/) | CLAIM-LEDGER.md, ios-and-workflow.md |
| S069 | [engine guide](https://www.bolna.ai/docs/agent-setup/engine-tab.md) | CLAIM-LEDGER.md, bolna-and-calls.md |
| S070 | [V2 schema](https://www.bolna.ai/docs/api-reference/agent/v2/get.md) | CLAIM-LEDGER.md, bolna-and-calls.md |
| S071 | [Call API](https://www.bolna.ai/docs/api-reference/calls/make.md) | CLAIM-LEDGER.md, bolna-and-calls.md |
| S072 | [Limits semantics](https://www.bolna.ai/docs/api-reference/limits.md) | CLAIM-LEDGER.md, bolna-and-calls.md |
| S073 | [catalog reference](https://www.bolna.ai/docs/api-reference/voice/get_providers) | CLAIM-LEDGER.md, bolna-and-calls.md |
| S074 | [voices](https://www.bolna.ai/docs/api-reference/voice/overview) | CLAIM-LEDGER.md, Ishara feasibility research.md, bolna-and-calls.md |
| S075 | [Number guide](https://www.bolna.ai/docs/buying-phone-numbers.md) | bolna-and-calls.md |
| S076 | [lifecycle](https://www.bolna.ai/docs/concepts/call-flow.md) | CLAIM-LEDGER.md, bolna-and-calls.md |
| S077 | [Security](https://www.bolna.ai/docs/concepts/security.md) | CLAIM-LEDGER.md, bolna-and-calls.md |
| S078 | [Custom TTS](https://www.bolna.ai/docs/custom-tts.md) | CLAIM-LEDGER.md, Ishara feasibility research.md, bolna-and-calls.md |
| S079 | [Contract](https://www.bolna.ai/docs/customizations/using-custom-llm.md) | CLAIM-LEDGER.md, Ishara feasibility research.md, bolna-and-calls.md |
| S080 | [developer resources](https://www.bolna.ai/docs/developer-resources/overview.md) | CLAIM-LEDGER.md, bolna-and-calls.md |
| S081 | [reference](https://www.bolna.ai/docs/developer-resources/sdks/web-call-api.md) | CLAIM-LEDGER.md, Ishara feasibility research.md, bolna-and-calls.md |
| S082 | [Guide](https://www.bolna.ai/docs/developer-resources/sdks/web-call.md) | CLAIM-LEDGER.md, bolna-and-calls.md |
| S083 | [FAQ](https://www.bolna.ai/docs/frequently-asked-questions.md) | CLAIM-LEDGER.md, bolna-and-calls.md |
| S084 | [Cost overview](https://www.bolna.ai/docs/get-started/what-it-costs.md) | CLAIM-LEDGER.md, bolna-and-calls.md |
| S085 | [Events](https://www.bolna.ai/docs/graph-agent/event-injection.md) | CLAIM-LEDGER.md, Ishara feasibility research.md, bolna-and-calls.md |
| S086 | [graph config with Hindi multilingual transcriber](https://www.bolna.ai/docs/graph-agent/full-example.md) | bolna-and-calls.md |
| S087 | [Static nodes](https://www.bolna.ai/docs/graph-agent/static-nodes.md) | CLAIM-LEDGER.md, Ishara feasibility research.md, bolna-and-calls.md |
| S088 | [Index](https://www.bolna.ai/docs/llms.txt) | CLAIM-LEDGER.md, Ishara feasibility research.md, bolna-and-calls.md |
| S089 | [outbound](https://www.bolna.ai/docs/outbound/making-calls.md) | CLAIM-LEDGER.md, bolna-and-calls.md |
| S090 | [Webhooks](https://www.bolna.ai/docs/post-call/polling-call-status-webhooks.md) | CLAIM-LEDGER.md, bolna-and-calls.md |
| S091 | [pricing](https://www.bolna.ai/docs/pricing/call-pricing.md) | CLAIM-LEDGER.md, bolna-and-calls.md |
| S092 | [Trial restrictions](https://www.bolna.ai/docs/pricing/outbound-calling-concurrency.md) | CLAIM-LEDGER.md, Ishara feasibility research.md, bolna-and-calls.md |
| S093 | [quickstart](https://www.bolna.ai/docs/quickstarts/api.md) | bolna-and-calls.md |
| S094 | [Current SIP guide](https://www.bolna.ai/docs/sip-trunking/overview.md) | CLAIM-LEDGER.md, bolna-and-calls.md |
| S095 | [TTS](https://www.bolna.ai/docs/text-to-speech.md) | CLAIM-LEDGER.md, bolna-and-calls.md |
| S096 | [Context variables](https://www.bolna.ai/docs/using-context.md) | bolna-and-calls.md |
| S097 | [Buildathon](https://www.bolna.ai/symphony/buildathon/) | CLAIM-LEDGER.md, Ishara feasibility research.md, bolna-and-calls.md |
| S098 | [Government VRS announcement](https://www.pib.gov.in/PressReleseDetailm.aspx?PRID=2098822) | CLAIM-LEDGER.md, Ishara feasibility research.md, ios-and-workflow.md |
| S099 | [W3C](https://www.w3.org/WAI/media/av/sign-languages/) | CLAIM-LEDGER.md, Ishara feasibility research.md, ios-and-workflow.md |
| S100 | [Machine-readable data terms](https://zenodo.org/api/records/4010759) | CLAIM-LEDGER.md, recognition-and-models.md |
| S101 | [archive](https://zenodo.org/records/4010759) | CLAIM-LEDGER.md, Ishara feasibility research.md, recognition-and-models.md |

### 23 October additions

Sources checked for the demo build decisions. Not renumbered into the S-series above.

| Exact checked URL | Used for |
|---|---|
| [Bolna docs index](https://www.bolna.ai/docs/llms.txt) | Page discovery |
| [Bolna custom LLM](https://www.bolna.ai/docs/customizations/using-custom-llm.md) | B08, Path B design |
| [Bolna event injection](https://www.bolna.ai/docs/graph-agent/event-injection.md) | B18, B19 |
| [Bolna static nodes & silence repeat](https://www.bolna.ai/docs/graph-agent/static-nodes.md) | B22 |
| [Bolna engine tab](https://www.bolna.ai/docs/agent-setup/engine-tab.md) | B22 |
| [Bolna hangup methods](https://www.bolna.ai/docs/outbound/hangup-calls.md) | B22 |
| [Bolna choosing TTS](https://www.bolna.ai/docs/concepts/choosing-text-to-speech.md) | D2 voice choice |
| [Bolna preferred models](https://www.bolna.ai/docs/pricing/preferred-models.md) | B21 |
| [Bolna what it costs](https://www.bolna.ai/docs/get-started/what-it-costs.md) | B21 |
| [Bolna Sarvam voice](https://www.bolna.ai/docs/sarvam-voice.md) | D2 |
| [Bolna Kalpa voice](https://www.bolna.ai/docs/kalpa.md) | D2 |
| [Bolna choosing telephony](https://www.bolna.ai/docs/concepts/choosing-telephony.md) | B20 |
| [Bolna buying numbers](https://www.bolna.ai/docs/buying-phone-numbers.md) | B20 |
| [Bolna API quickstart](https://www.bolna.ai/docs/quickstarts/api.md) | B20 |
| [Bolna make call API](https://www.bolna.ai/docs/api-reference/calls/make.md) | B20 |
| [Bolna stop call API](https://www.bolna.ai/docs/api-reference/calls/stop_call.md) | B19 |
| [Buildathon page](https://www.bolna.ai/symphony/buildathon) | H02 |
| [Apple AAC sample (.md)](https://developer.apple.com/documentation/avfaudio/adding-synthesized-speech-to-calls.md) | A20 |
| [MediaPipe Holistic Landmarker for iOS](https://developers.google.com/edge/mediapipe/solutions/vision/holistic_landmarker/ios) | D6 on-device recognition |
| [Cerebras rate limits](https://inference-docs.cerebras.ai/support/rate-limits) | H04 |
| [Cerebras models](https://inference-docs.cerebras.ai/models/overview) | H04 |
| [Cerebras change log](https://inference-docs.cerebras.ai/support/change-log) | H04 |
| [Heroku app sleeping](https://www.heroku.com/blog/app_sleeping_on_heroku/) | H03 |
| [Heroku request timeout](https://devcenter.heroku.com/articles/request-timeout) | H03 |
| [Heroku WebSockets](https://devcenter.heroku.com/articles/websockets) | H03 |
| [INCLUDE label map](https://raw.githubusercontent.com/AI4Bharat/INCLUDE/master/label_maps/label_map_include.json) | R16 |

## Retrieval limits and conflicts

- Jev's Context7-indexed text-only metadata conflicted with current live image docs; live provider docs win for this shipped change (M01–M02).
- The publicly retrieved iSign README establishes CC-BY-NC-SA-4.0 frontmatter and research/non-commercial/no-further-redistribution wording. Gated video access was not obtained. License/access-condition compatibility needs qualification before reuse (R08).
- LayaKit direct repository/raw retrieval failed. Only a registry pointer was inspected; no platform/packaging claim is made from inaccessible source (M08).
- INCLUDE original/current counts differ by five explained archive additions; mirror row counts are not extra independent validation samples. The mirror card/search row count is not a verified unique-video count; no mirror manifest was inspected (R03–R05).
- Current Bolna SIP docs supersede the stale no-SIP FAQ; static-cache timing is not dynamic synthesis, and provider `/audio/speech` direction matters (B02/B10/B14).
- Public docs did not establish standalone Bolna synthesis, SDK send-text/raw-audio/transcript methods, incoming native Phone audio access, or camera/AAC/captions composition. Bounded not-found is not proof that private/beta capabilities do not exist.
- The latest Apple availability page consulted targets iOS27. Actual installed iOS, exact locale menu, overlay behavior and current hardware routing remain uninspected.
- Inherited 62%/83% results have no reviewed experiment artifact. No source research substitutes for a new measured result or Deaf participant validation.
