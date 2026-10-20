# ISL recognition, datasets, and decision models for Ishara

> Historical source study, including inherited vocabulary and model assumptions.
> See the [research index](../research/README.md) for later studies and the
> [experiment record](../experiments/recognition.md) for executed local results.

Research checked 18 October 2026. Target: iPhone 17; installed iOS version unknown. This is feasibility research, with no model execution, training, checkpoint downloads, API inference, installation, or accuracy validation. Source-backed facts, inferences, and gaps are distinguished below.

**Controlling workflow correction:** the latest user clarification requires an ordinary cellular call from the user's own number directly to the clinic, with Ishara's synthesized speech injected into that existing Phone call. Bolna-originated calls, callbacks and two-call bridges are excluded. The platform researcher's candidate is Apple's AAC microphone injection plus system Live Captions. No API exposing the remote Phone audio or system caption text to Ishara has been verified; never assume the recognizer/decision model receives the receptionist's speech. Earlier appointment-form/relay ideas below are explicitly historical candidates, not requirements that override this clarification.

## 1. What recognition approach and data can support a bounded ISL demo?

### Takeaway

A small temporal landmark recognizer is the most credible baseline to investigate. Jev image verification is an experimental comparator, not a replacement whose ISL performance is established. Public isolated-word benchmarks do not establish continuous conversation performance, and the inherited 62% top-1 / 83% top-3 result remains unverified.

### Cited Findings

- **INCLUDE** contains 263 isolated signs. The original paper describes 4,287 videos and reports 94.5% INCLUDE-50 / 85.6% INCLUDE accuracy for its experiments. The current archive explains five later additions, bringing its files to 4,292; it specifies 3,475 training and 817 testing videos. Each recording contains one sign. Its metadata explicitly specifies **CC-BY-4.0**. These are dataset/paper facts, not Ishara measurements. [Paper](https://dl.acm.org/doi/10.1145/3394171.3413528); [archive](https://zenodo.org/records/4010759); [machine-readable license](https://zenodo.org/api/records/4010759)
- The [Hugging Face INCLUDE mirror](https://huggingface.co/datasets/ai4bharat/INCLUDE) surfaced a 5,250-row card/search count. No mirror manifest was audited; rows are not verified unique videos, additional signers, or independent validation examples. Use original archive manifests for source-clip accounting.
- The authors' code repository offers landmark preprocessing, training, and pretrained evaluation paths. The repository's **MIT code license** is separate from the dataset license. Artifact availability and current compatibility have not been exercised. [AI4Bharat repository](https://github.com/AI4Bharat/INCLUDE)
- **CISLR** covers roughly 4,700 words and proposes one-shot prototype recognition transferring features from ASL. Its dataset README explicitly states **CC-BY-NC-4.0** even though the repository metadata reports MIT. Use the explicit dataset section for data terms; the code badge cannot erase its non-commercial restriction. [Authors' repository](https://github.com/Exploration-Lab/CISLR); [EMNLP paper](https://aclanthology.org/2022.emnlp-main.707/)
- **iSign** reports 118,228 video–text pairs, with video-to-text, pose-to-text, text-to-pose, word-presence, and semantics tasks. The authors describe semi-automatic segmentation/transcription and validation of a 593-pair sample by certified ISL signers. This is useful research material with annotation noise, not a ready-made 25-word mobile classifier. [Paper](https://aclanthology.org/2024.findings-acl.643/); [project](https://exploration-lab.github.io/iSign/)
- The iSign dataset card frontmatter specifies **CC-BY-NC-SA-4.0** and the accompanying access terms specify **research/non-commercial use and no further redistribution**. The publicly fetched README establishes these statements; gated video access was not obtained. The card supplies video/pose information and recommends splitting by source `video_id` so adjacent segments do not leak across splits; this source grouping does not establish signer independence. Reconcile the stated license with additional access/redistribution conditions before bundling assets. [Dataset card](https://huggingface.co/datasets/Exploration-Lab/iSign); [README inspected](https://huggingface.co/datasets/Exploration-Lab/iSign/blob/main/README.md)
- **ISLTranslate** is a 31k continuous ISL–English sentence/phrase resource; its translation benchmark differs from isolated recognition. [Original paper](https://aclanthology.org/2023.findings-acl.665/)
- **ISL-CSLTR** describes 700 annotated videos for 100 sentences and seven signers. The abstract also gives a contributor breakdown that does not transparently reconcile to seven; inspect original metadata before relying on demographic counts. [Original dataset record](https://doi.org/10.17632/kcmpdxky7p)
- **2025 continuous ISL fingerspelling research** supplies 1,308 segments / 499 source videos / 70.85 minutes. Its ByT5-small baseline reports **82.91% character error rate**, which is an error rate, not 82.91% accuracy. This does not make arbitrary names and numbers solved for our demo. [Original paper](https://aclanthology.org/2025.wslp-main.6/)
- **2026 specialist recognition evidence:** a CVPR workshop paper uses temporal hand/body landmarks and reports 95.88% top-1 on the original INCLUDE split versus 83.82% on its proposed pseudo-signer split, and 19.20% on CISLR. Its signer protocol approximates groups from recording adjacency because explicit identity metadata is missing; do not call it fully verified signer independence. Its fine-tuned LLaVA-NeXT comparison reaches 32.24%; tested zero-shot VLMs perform near zero. These results are not tests of Jev. The model uses 42 hand + 23 upper-body points and less than 10M trainable parameters. No validated iPhone runtime or downloadable checkpoint was established in this review. [Original paper, sections 3–4](https://openaccess.thecvf.com/content/CVPR2026W/MSLR/papers/Varanasi_Isolated_Sign_Language_Recognition_via_MediaPipe_Landmarks_A_Case_Study_CVPRW_2026_paper.pdf)
- **MediaPipe iOS** supports asynchronous live-stream Hand Landmarker results; hand landmarking produces geometry, not ISL glosses. Its default maximum hand count is one, so two-handed signing requires deliberate configuration. A temporal model and further body/face features remain separate design decisions. [Official iOS guide](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/ios); [landmark model description](https://developers.google.com/edge/mediapipe/solutions/vision/gesture_recognizer/index)
- **ISLRTC's FAQ Q23 permits research, teaching, and development of ISL technology** on two conditions: no resale/profiteering and proper acknowledgment. It describes 10,000 dictionary terms, regional variants, synonyms, and English words without one-to-one corresponding signs. These terms are more informative than assuming every online video is freely reusable. [Official FAQ](https://islrtc.nic.in/faq/)

### Inferences

- Proposed baseline pipeline: capture → framing/quality checks → landmarks → temporal segmentation → isolated candidate distribution → reject/confirm/commit → bounded sentence construction. A detector says where hands are; a recognizer says which sign; segmentation says when a sign begins/ends. All three must work to approach automatic turn-taking.
- A landmark temporal CNN/GRU/compact Transformer is a candidate to compare, not a predetermined architecture. A simple per-frame gesture classifier cannot establish signs distinguished by direction or motion. Landmark-only systems may lose hand texture, occlusion detail, and non-manual linguistic information; retain a clear evidence boundary rather than claiming universal translation.
- Continuous input introduces transitions, idle gestures, self-corrections, repetitions, camera adjustment, and out-of-vocabulary signing. A model trained only on neatly clipped signs may classify all of those as one of its known labels. An explicit unknown/no-sign pathway and duplicate suppression must be evaluated before automatic speech.
- Signs are not necessarily English words, and one sign may require a phrase or contextual interpretation. A 25-label demo should be called constrained sign-mediated communication rather than unrestricted ISL translation.
- In a finite-choice reranker, a true sign absent from the recognizer's top-k cannot be recovered simply by sorting those k options. Include `none_of_these`, retain access to wider candidates if justified, and measure candidate recall separately from reranking accuracy.
- Data audit before implementation: exact concept/variant; source/license; number of clips; signer/session identities where known; front-camera mirroring/orientation; timing and preprocessing; held-out real-device examples. An archive label name alone is insufficient evidence of semantic coverage.
- Keep a phone propped so both hands, upper torso, and face can be visible as the leading demo hypothesis. Holding the phone occupies a hand and changes the recognition domain. Natural one-handed ISL support cannot be inferred from two-handed training clips.
- Public dictionary examples can support a reference library, but one clean recording per new sign is not adequate evidence for a signer-general classifier. Separately check exact asset attribution and redistribution terms, particularly for bundled reference videos.

**Isolated classifiers versus bounded natural phrases:**

- An isolated-word classifier labels an already bounded sequence. A temporal encoder can model movement *within* that sequence without solving the boundaries between successive signs, coarticulation, or ISL-to-English translation. The cited specialist's preprocessing trims the outer frames of individual clips; its reported classification accuracy is not evidence for a continuously signing user. [Specialist paper, sections 3.2 and 4](https://openaccess.thecvf.com/content/CVPR2026W/MSLR/papers/Varanasi_Isolated_Sign_Language_Recognition_via_MediaPipe_Landmarks_A_Case_Study_CVPRW_2026_paper.pdf)
- ISL phrase/sentence data **does exist**: iSign provides sentence/phrase pairs and both video-to-text and pose-to-text tasks; ISLTranslate provides continuous sentence/phrase pairs. The gap is verified coverage and generalization for *our* bounded phone dialogue, not the absence of continuous ISL datasets. [iSign](https://exploration-lab.github.io/iSign/); [ISLTranslate](https://aclanthology.org/2023.findings-acl.665/)
- Do not ask users to sign in English gloss order and call it natural ISL. ISL's own grammar and simultaneous non-manual information mean “recognize English word labels, then concatenate” is an inadequate language model. [Google's linguistic explanation](https://deepmind.google/blog/putting-sign-language-ai-into-users-hands/)
- **Engineerable hypothesis, not measured capability:** audit existing continuous corpora for a few naturally signed appointment-relevant intents; compare whole-phrase temporal classification/retrieval or an adapted published translation baseline on those phrase clips. An exact finite phrase classifier can emit an approved English sentence without mapping each sign to an English word or enforcing English order. It still requires enough examples/variants, appropriate boundaries, an unknown pathway, and held-out signer/session checks.
- **Engineerable hypothesis, not measured capability:** an automatic boundary detector plus a temporal candidate buffer might accept a short naturally signed phrase, delay commitment until its end, and map it to a supported intent. Training it on isolated clips concatenated synthetically does not demonstrate real coarticulation or natural transitions. That technique can be evaluated as augmentation, not presented as a substitute for continuous examples.
- Existing phrase data could support a bounded research prototype without new Deaf recordings **if** exact or semantically appropriate phrases, usable terms, sufficient examples, and suitable held-out evaluation are available. This audit has not established those conditions. Without fluent participant/expert review, the team cannot validate that a newly assembled phrase is natural, that a corpus translation exactly expresses an appointment intent, or that hearing reenactments preserve its grammar. This is an uncertainty boundary rather than a claim that the prototype is impossible.
- If phrase coverage is absent, sign-by-sign recognition with deliberately separated inputs may be a demonstrable fallback, but it imposes a new signing workflow. Treat that as an explicit demo limitation requiring the user's choice. A requirement for visible pauses, tap-to-delimit, or English-order gloss input must not be hidden behind the word “seamless.”

### Gaps

- No underlying artifact, script, dataset manifest, signer split, or confusion matrix for the inherited **26-word 62%/83% baseline** was reviewed. Do not claim it was reproduced, calibrated, or validated. Top-3 is candidate recall under that experiment, not automatic speech accuracy.
- Exact target-vocabulary coverage and signer counts were not audited from video files. No large dataset was downloaded. Open questions include sign variants for SORRY, PLEASE, PAIN, HELP and whether the chosen versions match the demo signer.
- iSign's public README establishes CC-BY-NC-SA-4.0 metadata plus research/non-commercial/no-further-redistribution wording. Gated video access was not obtained, and compatibility of the stated license with additional access/redistribution conditions needs qualification before reuse. RKMVU-linked clips were not assigned a license from the identity of their host or from ISLRTC's separate permission.
- No deaf participant means usability, language suitability, caption reading preferences, and natural signing cannot be validated here. Hearing team members copying reference signs can test plumbing; they cannot validate the stated persona.

## 2. Where do Jev, Laya, Google sign models, and generation actually fit?

### Takeaway

Use a decision model for bounded choices about already observed evidence. Jev now accepts images experimentally, and there are actual community Laya iPhone/Core ML paths; earlier blanket claims that Jev is text-only or Laya has no iPhone route require correction. Neither capability establishes ISL recognition quality or target-device performance.

### Cited Findings

- **Jev image API:** the live guide enables images with `TypeSafe-Danger-Zone-Images: true`. Top-level `assets` references may appear in state, instructions, or criteria; PNG/JPEG uploads can represent an ordered history of frames. Jev 1.13 and 1.14 accept images; Box requires 1.14. These are image requests, not a documented video-stream input. [Current image guide](https://docs.typesafe.ai/images)
- **Version update:** current live docs map `jev-latest` to stable 1.13 and `jev-preview` to 1.14, released 14 October. Responses disclose the actual version, and aliases can change. Pin versions when evaluating thresholds. [Current model documentation](https://docs.typesafe.ai/models)
- **Confidence correction:** Jev Choice confidence is a transformation of the largest returned option probability, relative to a uniform distribution. It is not an independently measured correctness detector. The docs explicitly recommend testing domain-specific thresholds. [Confidence documentation](https://docs.typesafe.ai/confidence)
- **Context7 discrepancy:** resolve/query against `/typesafe-docs/typesafeai` returned text-only 1.13 metadata, conflicting with current live image documentation. Prefer the current provider page for this newly shipped capability; do not use the index as proof that images do not work. [Indexed source](https://github.com/typesafe-docs/typesafeai/blob/main/docs/12-models.md); [live correction](https://docs.typesafe.ai/images)
- **Laya upstream:** text/structured-state, non-autoregressive typed decisions (`choice`, `score`, `noul`), Apache-2.0 code/weights. Current upstream includes ONNX support and TypeScript/browser paths. Its own model card illustrates overconfident failure on some non-English text; multilingual support must be checked with the appropriate checkpoint. No image/sign input path was established. [Upstream repository](https://github.com/nandhakishorm/laya); [model card](https://huggingface.co/convaiinnovations/laya)
- **Specific `laya-mlx` runtime:** independent Python MLX port requiring Apple Silicon/macOS 14+/Python 3.11+. Its published short-question results are 13.42 ms p50 English and 7.39 ms multilingual on a 40-GPU-core M3 Max / 128 GiB machine, excluding model loading, with peak allocations around 944/688 MiB. These are Mac benchmark boundaries, not iPhone latency promises. [Primary repository](https://github.com/mizorewww/laya-mlx)
- The user-linked blog agrees that Laya MLX is a bounded decision runtime, not a prose generator; it is secondary and not independent iPhone validation. [Supplied article](https://aiidelist.com/blog/what-is-laya-mlx)
- **Actual iPhone route exists in source:** `laya-ANE` publishes a SwiftUI iOS demo and preparation script. Its iOS instructions target iOS 17+, default to a 421M typed-decisions conversion, 160-token total capacity, FP16 plus six-bit palettization, and require local model generation and Xcode signing. This is evidence of an implementation candidate, not proof it runs correctly on the user's iPhone 17. Tiny dummy bundles explicitly return untrained outputs. [Repository](https://github.com/vipuldivyanshu92/laya-ANE); [iOS instructions](https://raw.githubusercontent.com/vipuldivyanshu92/laya-ANE/main/ios/README.md)
- **Other Apple paths:** FluidInference publishes a 322M multilingual Core ML conversion and Swift integration. Its model card reports complete FP16 buckets around 614 MB and int8-embedding variants around 448–453 MB. Parity and timing were measured on M5 Pro/macOS, not iPhone; aggressive quantization failed some parity gates. [Primary model card](https://huggingface.co/FluidInference/laya-coreml)
- **Native Swift does not automatically mean iOS:** MstyAI's `laya-mlx-swift` explicitly targets Apple Silicon Macs/macOS 14+, with a roughly 804 MiB model download. It does not establish an iPhone integration. [Primary repository](https://github.com/MstyAI/laya-mlx-swift)
- `LayaKit` is listed in third-party registries as a Swift/Core ML port, but direct repository/raw fetches failed during research; do not present its packaging/platform matrix as independently inspected. [Registry pointer](https://systemonemodels.org/examples/tools/layakit/)
- **Google update:** Google announced SL2T on 12 August 2026, trained over 100,000 hours across more than 50 sign languages. Initial deployment is ASL→English in Gboard/Live Transcribe on Pixel 11; landmarks are extracted on-device and sent to a server. The announcement does not establish public weights, a developer API, ISL product support, or an iPhone integration. Training-language breadth and shipped-language coverage are different claims. [Google DeepMind announcement](https://deepmind.google/blog/putting-sign-language-ai-into-users-hands/)
- **SignGemma access:** official forum responses said no release/access in October 2025 and no specific timeline in January 2026. Later community posts are questions, not new release statements. No current primary public SignGemma checkpoint/API was established here. Do not substitute Google SL2T, generic Gemma, or third-party claims for a released SignGemma endpoint. [Access thread](https://discuss.ai.google.dev/t/how-to-get-access-to-signgemma/106766); [release-date thread](https://discuss.ai.google.dev/t/signgemma-release-date/113794)

### Inferences

| Component | Appropriate bounded job | Boundary to preserve |
|---|---|---|
| Temporal specialist recognizer | Distinguish a supported sign from observed motion | Must reject idle/unsupported/poorly framed input |
| Jev images | Compare an uncertain frame sequence against reference candidates | Experimental; sparse frames can miss discriminating motion |
| Jev text / Laya | Rerank plausible candidates using the user's own signs and an explicitly selected call scenario; select a response template | No receptionist question/transcript is available to this app unless an API or explicit user input is separately established; context cannot invent user intent |
| Deterministic templates | Insert confirmed semantic slots/profile data into approved phrases | Cannot express arbitrary unsupported meaning |
| Generative text model | Optional phrasing or caption simplification after semantic commitment | Must preserve dates, times, negation, speaker, uncertainty; never add medical details |
| Local speech synthesis / Apple AAC injection candidate | Speak exactly the committed utterance into the existing Phone call | No Bolna call bridge; no separate agent paraphrasing or negotiating on the user's behalf |

- Proposed Jev visual experiment: candidate references plus timestamped query frames; choices include known signs, `none_of_these`, `not_signing`, `insufficient_view`. Compare visual-only with context-assisted judgments. This is a hypothesis needing clips, not an assertion that Jev understands ISL.
- For a small appointment demo, templates may remove a generation hop. Choosing an existing response and filling a verified time is different from unrestricted language generation. Evaluate a generative model only if actual workflow requirements demand it.
- Example of an architecture to reject under current constraints: “receptionist offers 4 pm → decision model extracts 4 pm → generates acceptance.” Ishara has no verified feed of that receptionist utterance. The user may read system captions and deliberately sign YES, but the app cannot safely add “four o'clock” from information it never received. A nod while reading, a transition inside another sign, or a likely booking preference is insufficient even if call context later becomes available.
- Evaluate the iPhone Laya route as an optional decision-layer spike, not a dependency for recognition. Tokenizer/prompt formatting, probability calibration, precision parity, memory, heat, cold start, and camera concurrency all matter. Community README existence is not a shipped app guarantee.
- A remote decision server on a demo Mac could be an explicitly disclosed fallback. It is a deployment choice, not equivalent to on-device execution or offline support.
- Cloud images expose frames with a face and body. Landmark-only local decisions reduce transmitted raw imagery but do not make coordinates inherently anonymous. The image verifier should be optional until quality and privacy tradeoffs are understood.

### Gaps

- No paid Jev request was made. Image latency, accuracy, retention details for the intended plan, request-body scaling with multiple reference sequences, and the most appropriate SDK version remain integration checks.
- No iPhone performance or conversion parity was tested. The iPhone-oriented six-bit path and FluidInference's stricter quantization results differ in model/implementation/test coverage; do not assume either validates the other.
- Generic Gemma can be investigated for generation separately; no target-specific checkpoint/runtime/latency recommendation follows from this review. SignGemma and SL2T must not be described as available ISL engines without new primary evidence.

## 3. What vocabulary, interaction policy, and comparison plan are defensible?

### Takeaway

The inherited vocabulary arithmetic can be reconciled, but 25 signs is a capacity target rather than a validated workflow. Natural interaction requires automatic sign boundaries and a reliable unknown pathway; reducing taps by guessing would defeat the intended interface.

### Cited Findings

- The vocabulary/baseline inputs below are inherited project claims from the user's brief and updates, not new dataset verification. Original 26: Hello, Thank you, How are you, Good Morning, I, you, we, good, bad, happy, sad, sick, Doctor, Hospital, Restaurant, Medicine, Money, Bathroom, Telephone, Bus, Train, Today, Tomorrow, Mother, Father, Friend. Proposed operation: remove Tomorrow/we/Money/Friend/Train; add SORRY/PLEASE/PAIN/HELP. Arithmetic: 26 − 5 + 4 = **25 classifier labels**, then two separate head inputs. Sources: user-supplied `ishara-readme-prompt.md` and `ishara-updates.md`, local materials not distributed in this repository.
- The literature distinguishes isolated recognition from sentence-level translation; ISLRTC's dictionary documents variants and non-one-to-one English mappings. This is why label count alone cannot define conversational coverage. [iSign project tasks](https://exploration-lab.github.io/iSign/); [ISLRTC FAQ](https://islrtc.nic.in/faq/)

### Inferences

**Reconciled inherited candidate inventory, not frozen requirements:**

1. HELLO
2. THANK_YOU
3. HOW_ARE_YOU
4. GOOD_MORNING
5. I
6. YOU
7. GOOD
8. BAD
9. HAPPY
10. SAD
11. SICK
12. DOCTOR
13. HOSPITAL
14. RESTAURANT
15. MEDICINE
16. BATHROOM
17. TELEPHONE
18. BUS
19. TODAY
20. MOTHER
21. FATHER
22. SORRY
23. PLEASE
24. PAIN
25. HELP
26. YES — separate proposed deliberate head-nod input.
27. NO — separate proposed deliberate head-shake input.

- APPOINTMENT is supplied by the chosen call purpose, not a classifier label. A date/time picker can supply a desired slot before the call. That does not cover accepting a different slot or answering an unforeseen question.
- This inventory still includes several low-utility appointment words (e.g. BUS, RESTAURANT, family labels) while lacking direct repair/call-control concepts such as WAIT, REPEAT, CANCEL, FINISH or later/tomorrow. Do not replace labels silently; use dialogue coverage and data availability to decide what earns a slot. A wider face-to-face demo could justify a different inventory.
- Nod/shake are tentative interaction design, not linguistically validated YES/NO classifiers. Facial/head movement can participate in signing, overlap with ordinary listening, and change meaning with timing. Wave-to-send or nod-to-accept adds conflicts with greetings and discourse gestures. Avoid adding explicit send/hold gestures by intuition while calling the flow natural.
- Candidate interactions to investigate: automatic commitment after a stable sign boundary; show top-3/re-sign only on uncertainty; no-sign/unsupported input stays silent; clear but nonintrusive recognized-content feedback; a visible option to repair the last utterance. The exact visual/haptic design requires testing, not inference from model scores.
- A **pending utterance buffer** can allow correction/undo before speech starts. Once audio has entered the Phone call, undo cannot retract what the other person already heard; it can stop unsent/queued audio and send a deliberate correction. Automatic speech therefore trades commitment delay against mistaken irreversible utterances. Include that delay in finish-to-audio metrics instead of reporting only model inference.
- Head nods/shakes need **intent gating**, not an always-on YES/NO mapping: detect a deliberate response in an appropriate interaction state and distinguish it from grammar, listening motion, or a transition. A new supported word, an unknown word, an idle gesture, and a partial phrase must not all collapse to the nearest known class. If the app cannot establish deliberate intent, abstention or visible confirmation is preferable to fabricated speech.
- With no app-readable incoming Phone audio/transcript, a response-state gate cannot silently infer “the receptionist just asked a yes/no question.” The system can use its own outgoing history, user-selected scenario, and explicitly recognized user input; system captions provide information to the human, not to that model. This limits automatic context expansion and argues for utterances that preserve exactly what was observed rather than adding unobserved dates, names, or proposed slots.
- Return captions are a system Live Captions platform candidate, not an assumed app-owned transcript. A caption simplifier would require an actual text feed that has not been established. Reading captions does not supply the decision model with their content. English literacy remains an unvalidated persona assumption.

**Comparison plan — proposed experiments only, none run:**

| Variant | Purpose | What must be held constant |
|---|---|---|
| A: specialist recognizer + explicit rules/templates | Baseline with fewest moving components | Same clips, supported inventory, segmentation, output policy |
| B: A + Jev text or Laya context reranking | Determine if user-sign history and an explicitly chosen scenario reduce corrections | Keep original visual scores; include context-mismatch examples; no remote call transcript |
| C: A + Jev image verification on uncertainty | Test added visual evidence rather than a confidence decoration | Same uncertainty cohort; reference variants separated from test signers |
| D: Jev image-only bounded recognition | Honest direct comparator if worth testing | Same sample/signer splits and unknown options |

**Data/evaluation requirements:**

- Split by real signer where available and additionally by recording session/source video. Keep demo-user calibration separate from held-out sessions. If identity metadata is absent, label results signer-overlapping/unknown or explicitly approximate; do not manufacture a signer-independent claim.
- Include supported isolated signs, short sequences/transitions, idle hands, camera adjustment, partial framing, occlusion, wrong/unsupported signs, non-manual movement and self-corrections. Add context deliberately suggesting a wrong sign to reveal hallucinated reranking.
- Report top-1 and top-k per class; candidate recall; unknown rejection and false accept rate; wrong automatically spoken utterances per 100 committed utterances; corrections/confirmations per turn; duplicate speech; task completion; onset/end segmentation errors. Ground-truth semantic error takes priority over score confidence.
- Measure signer-finish→committed-text→first audible speech separately at p50/p95, plus camera frame rate, warm/cold start, memory, sustained temperature and battery. Include network and relay/TTS time. Mac decision inference numbers cannot substitute for end-to-end iPhone turn latency.
- Establish thresholds on held-out development examples, then freeze before final test. Assess calibration at each chosen confidence threshold; do not multiply recognizer/Jev probabilities as though they were independent.
- Acceptance targets must be chosen before experiments, with wrong automatic speech treated more seriously than a recoverable request to re-sign. Report absolute counts and denominators with small samples.

### Gaps

- Current vocabulary semantics, training coverage, phrasing templates, sign boundaries, and gesture controls still require a source-clip audit and workflow review.
- No participant validation or actual model/phone/AAC-injection experiment has been completed. This research supports choosing experiments and architecture options; it does not pass their gates.
- No public model was found that can be honestly asserted to solve natural, unrestricted, low-latency ISL conversation on iPhone 17 as a drop-in dependency today.
