# Everyday workflows and product directions for Ishara

## 1. Which everyday communication barriers justify this product, and what already exists?

### Takeaway
The strongest specific opportunity is not “Deaf people cannot communicate.” It is a short, necessary conversation in which another person insists on voice, while the user wants to respond in ISL without recruiting a family member. Ride pickup calls are particularly well grounded in Indian user research; service-counter conversations are a credible adjacent direction. Neither is an uncontested market or a validated Ishara persona.

### Cited Findings
- An Indian study used 15 interviews and 131 survey responses from employed DHH adults. Participants described unwanted ride-hailing/delivery calls, failed text exchanges, cancelled rides, and reliance on hearing intermediaries. Its data were collected in 2022; it does not establish every platform's present behavior or all Deaf adults' needs. — [Primary study, Sridhar et al.](https://roshni-poddar.github.io/assets/pdf/interact23a-sub1087-cam-i7.pdf)
- The same study describes caption-reading pace, Indian-name transcription, language proficiency, and privacy/agency problems with informal intermediaries. These are reasons to test the return channel and correction workflow, not evidence that every Deaf signer has limited literacy. — [Primary study](https://roshni-poddar.github.io/assets/pdf/interact23a-sub1087-cam-i7.pdf)
- NAD India explicitly identifies interpreters as communication access and names hospitals, doctors, government offices and transport information as accessibility settings. — [National Association of the Deaf India](https://nadindia.org/Projects/Accessibility)
- SignAble already advertises human ISL video remote interpretation for shops and doctors' offices, and video relay calls to landline/mobile recipients who need not install its app. Its individual service page describes registration and subscription. These are vendor claims, not independently measured availability or performance. — [SignAble individual services](https://signable.live/for-individuals-communicate-with-the-deaf/)
- ISLRTC announced VRS integration into national helpline 14456 in February 2025, connecting Deaf users with hearing people and service providers through ISL interpretation. — [Government announcement](https://www.pib.gov.in/PressReleseDetailm.aspx?PRID=2098822)
- Existing services are improving ordinary workflows. Uber documents text-only preferences for Deaf couriers and automatic translation of messages across more than 50 languages. These claims do not establish equivalent options for every Deaf passenger or every Indian service. — [Uber's own accessibility announcement](https://www.uber.com/us/en/newsroom/globalaccessibilityawarenessday2024/)
- EnAble India's newsroom documents its Purple Rides collaboration with Namma Yatri; a contemporaneous report specifically describes disabling driver calls for hearing-impaired riders. Treat the exact no-call behavior as secondary reporting, not a tested current feature. — [EnAble India](https://new.enableindia.org/newsroom/); [The Hindu report](https://www.thehindu.com/news/cities/bangalore/namma-yatri-app-launches-disability-friendly-services/article67384017.ece)
- Some Deaf people prefer sign language, some prefer captions, and not all Deaf people know sign language. Signing includes facial expression, body position and hand/arm movements. — [W3C guidance](https://www.w3.org/WAI/media/av/sign-languages/)
- WFD says Deaf communities must participate in sign-language AI decisions, including evaluation of real-world performance and data ownership. It does not endorse this project or imply automated systems can replace interpreters. — [WFD 2025 AI workshop account](https://wfdeaf.org/artificial-intelligence-and-sign-languages/)
- WFD distinguishes VRS from VRI and supports user choice of remote or on-site interpretation; its position paper cautions against replacing face-to-face interpreting in high-stakes medical/legal settings. — [WFD accessibility position paper](https://wfdeaf.org/wp-content/uploads/WFD-Postion-Paper-on-Accessbility-12-Feb-2019-Updated.pdf)

### Inferences
- A defensible impact claim is a bounded increase in communication agency: “The user answered and corrected a voice-only pickup conversation themselves.” It is not an estimate of millions served, the elimination of interpreters, or a claim that no alternatives exist.
- Demonstrate why captions alone are insufficient by letting captions handle hearing speech while the user actually initiates, disagrees, and repairs through supported signing. If typing is faster/preferred for a particular user, Ishara should not force signing for spectacle.
- Avoid pitching diagnosis, consent to treatment, prescriptions, legal advice or emergency interpretation. Clinic reception/check-in is administrative, but misunderstandings still matter. Retail pickup/returns are lower-stakes test settings.
- AI should preserve the user's intended message and explicitly request missing content. It should not fill unknown signs with a plausible appointment, landmark, price, or consent because an LLM expects it.
- A visible unknown/repair episode is valuable demo evidence: it distinguishes a communication tool from a prerecorded sequence. That is a product judgment, not a published judging criterion.

### Gaps
- No Deaf participant has reviewed Ishara. We cannot claim that the proposed framing, camera posture, input mode, captions, agency controls or convenience are preferred.
- The study is a working, relatively educated sample, not a population prevalence estimate. This review did not obtain current field observations of Indian driver/receptionist behavior.
- Current interpreter availability, subscription prices and average waits were not measured. Do not claim instant AI outperforms a human service on these dimensions.
- The parent technical track is investigating Bolna interfaces. Product roles below are hypotheses contingent on its documented/OSS capabilities; they are not executed integrations.

## 2. Which concrete product variations deserve consideration?

### Takeaway
Keep the ordinary-call sidecar as the preferred direction if the technical track establishes a meaningful Bolna speech path. Focus its first story on one common task rather than a generic translator. Use a face-to-face counter bridge as the strongest pivot if call/caption composition fails; appointment delegation is a different product with stronger native Bolna fit but reduced direct conversational agency.

### Cited Findings
- The earlier research pack documents Apple AAC injection into an existing call, the app's lack of access to unrelated Phone-call incoming audio, untested camera/caption composition, and incomplete return-language coverage. This note does not replace those constraints with a claim that an app can listen to the call. — [Apple AAC guide](https://developer.apple.com/documentation/avfaudio/adding-synthesized-speech-to-calls); [Apple DTS incoming-audio restriction](https://developer.apple.com/forums/thread/841340)
- The communication situations below are selected from Indian barriers and existing VRI/VRS service examples, while their particular interfaces and demos are our proposed designs. — [Indian study](https://roshni-poddar.github.io/assets/pdf/interact23a-sub1087-cam-i7.pdf); [SignAble](https://signable.live/for-individuals-communicate-with-the-deaf/)

### Inferences

#### A. “Where are you?” — ordinary incoming pickup call

**Situation:** A driver/courier calls to locate the user. The task is finding each other, not arranging an entire journey or giving free-form directions.

**Normal steps:** The user answers an ordinary call, opens Ishara, positions the camera, reads supported system captions, signs a short response, and ends the call through Phone. The caller uses their usual phone and does not install an app. This is one explicit app transition, not an invisible Dynamic Island translator.

**Memorable demo:** Caller is at the wrong entrance. User signs an approved location from a small, disclosed set, asks the driver to wait, reads the correction question, then corrects the entrance. The caller arrives at the agreed place. A deliberate ambiguous input causes Ishara to ask the signer to repeat before any wrong location is spoken.

**Bolna's central job, conditionally:** A text-input/audio-output session turns recognized and approved content into faithful recipient-language speech; controls utterance order, cancellation and pauses. The sidecar cannot give Bolna incoming-call understanding it does not possess. It must not automatically respond to “east or west?” unless the user supplies the answer. A translation/session route needs the technical team's proof, including exact-content behavior and latency.

**Why use it:** Short live replies can avoid recruiting someone nearby when the other party keeps calling. The advantage over a saved phrase board must come from signed input and meaningful correction, not a hidden selection of prerecorded sentences. The advantage over captions is outgoing agency.

**Friction/risk:** This is physically the hardest setting: two-handed signing, phone positioning outdoors, poor lighting, noise, urgency and incoming-language support. Demonstrating at a desk does not prove sidewalk usability. Do not let an attractive small vocabulary disguise these costs. A disclosed set of prepared locations may help an honest demo, but cannot establish arbitrary-location recognition.

**Counterargument:** In-app translated messages or no-call preferences may already solve the problem more cheaply. Ishara is most useful when a voice conversation still occurs, not when it recreates accessible platform chat.

#### B. “I'm here for my appointment” — face-to-face service-counter bridge

**Situation:** User is physically at clinic reception, a collection counter or a shop; employee does not know ISL. For the first demo choose clinic administrative check-in OR a retail return, not diagnosis or a general pharmacy consultation.

**Normal steps:** Open Ishara and put the phone on the counter facing the signer. Sign a supported request; speech plays to the employee. The employee speaks normally into the same interaction; the app displays a readable return channel. The user can correct or ask for repetition.

**Memorable demo:** User checks in for a scheduled visit. Reception says the booking is for the wrong day. User rejects that interpretation, supplies the supported correction, and gets the appointment located. Alternatively, a retail return demonstrates “exchange, not refund” and the employee's stock question without medical context.

**Bolna's central job, conditionally:** Manage both local spoken turns and the text derived from supported signing, including multilingual hearing-side ASR/TTS and turn control. Compared with the Phone sidecar, the application owns the local microphone interaction; parent technical research must validate the actual Bolna adapter and transcript/event interfaces. Echo suppression must prevent the agent from hearing and responding to its own speech.

**Why use it:** Staff keep speaking; signer keeps signing; neither needs a dedicated business integration or another installed client. The app can mediate a bounded exchange rather than requiring the user to type a paragraph for every turn.

**Friction/risk:** Counter space, camera angle, ambient speech/privacy, caption literacy, network latency, and local-language accuracy. Full bilateral ISL is not established: captions are not speech-to-ISL. Simplified text/cards may aid a specific bounded task but do not create a universal return channel.

**Counterargument:** Easier to engineer than native call composition, but has less novelty against ordinary speech-to-text and human VRI. It wins credibility only through reliable signed expression and correction, not branding a speech assistant as a universal interpreter.

#### C. “Let me arrange my own appointment” — ordinary outbound call sidecar

**Situation:** User calls a familiar local clinic, salon or repair shop from their own number and conducts the conversation personally.

**Normal steps:** Select/phone the business normally; open foreground Ishara; sign appointment intent; read system captions; propose and reject times; explicitly confirm; hang up normally. Use Contacts/pickers or an existing profile for names/numbers/date where appropriate, while keeping those mechanisms visible.

**Memorable demo:** Business offers a time the user cannot attend. User rejects it, proposes another supported slot, corrects one misunderstood detail, then confirms the final arrangement. Booking is not inferred by a model that cannot hear the conversation.

**Bolna's central job:** Same conditional outgoing speech role as A. Bolna may translate an approved utterance into the receiver's spoken language, but cannot interpret incoming Phone audio through magic. The product should demonstrate the difference this voice/session layer makes; a redundant network hop for an unchanged canned phrase is a weak integration story.

**Why use it:** Most faithful to the founder's original vision and preserves the user's control over the conversation and existing calling identity. Does not require a clinic portal.

**Friction/risk:** More dialogue coverage than pickup, unexpected names and policy questions, explicit slot representation, no app-readable incoming transcript, and unknown Hindi/mixed-language caption support. Distinguish requesting a slot from completing a booking.

**Counterargument:** Unless outgoing Bolna integration is genuinely demonstrated, Apple AAC + local TTS could explain most of the demo. The team should not quietly switch to a provider-originated call and still describe it as this option.

#### D. “Please book it for me” — signer-authorized task delegation

**Situation:** User provides a bounded request and preferences; Bolna calls the business and performs the task, escalating decisions outside the permission envelope.

**Normal steps:** User chooses a business, signs a supported request, supplies date/time preferences through signing or pickers, approves a concise request summary, and delegates. The agent calls, collects offers, pauses for user decisions when required, then returns a factual result. If a business offers an unapproved slot, the agent must not accept on the user's behalf.

**Memorable demo:** Agent requests an appointment; business offers a time outside the user's allowed range. User sees the offer in an accessible interface and signs a counterproposal. Agent resumes and obtains an explicitly approved result. Show a failed/no-availability outcome as a valid result rather than inventing success.

**Bolna's central job:** Actual voice conversation, multilingual ASR/TTS, phone lifecycle, task state, tool calls and escalation. This is much more integral than calling a TTS service, but technical support for supervised pause/resume must be verified.

**Why use it:** Eliminates repeated short administrative calls while giving the user control over commitments. Could be useful to users who already ask someone else to make these calls.

**Friction/risk:** This is an explicit pivot: the user is delegating rather than personally conversing through their normal call. Service-originated calling, number/trial/account requirements and disclosure apply. A caption-only approval surface may still exclude the intended signer. Asynchronous updates can be missed.

**Counterargument:** Risks becoming a generic appointment bot with a sign-input launcher. The distinctive value must be accessible supervision and retained consent, not an unproven promise of full sign recognition.

#### E. “Talk through Ishara” — app-owned live relay call

**Situation:** User selects a number within Ishara and remains actively in a live conversation; Ishara/Bolna carry the media and call rather than augmenting the existing Phone call.

**Normal steps:** Pick the person, start an app session/call, sign, read application-controlled incoming captions, repair, hang up in the app. Receiver can retain an ordinary telephone endpoint if provider telephony supports the route; do not claim the caller's own number or incoming reachability without proving them.

**Memorable demo:** A real-time repair-service conversation contains a misheard part/date; the signer corrects it and sees a persistent readable conversation history. Bolna can use the actual incoming audio/transcript here, unlike the unrelated Phone sidecar.

**Bolna's central job:** Own the voice session and media, handle transcription/TTS/turn-taking, and connect signed utterances to the remote conversation. Technical routing and a non-autonomous relay policy remain to be demonstrated.

**Why use it:** Gives engineering control over both directions, language processing and visual context, potentially supporting a better accessible conversation than a system-caption-only sidecar.

**Friction/risk:** Explicit pivot from normal Phone/Contacts calling and own-number identity; onboarding, call setup, provider availability/cost and recipient identity may differ. It competes directly with established relay/caption calling products and human VRS.

**Counterargument:** Better control for engineering does not by itself equal seamlessness for users. If we cannot explain the concrete benefit over existing VRS and translated text, the sign interface alone is a weak differentiation.

### Gaps
- All demos are proposed, not demonstrations that the present vocabulary, licensed clips, recognition model, Bolna adapters or target device support them.
- Person/business names, arbitrary landmarks, free-form symptoms and unusual questions are outside a small phrase recognizer unless separately solved. Do not include them in live promises without evidence.
- This assignment did not evaluate how iPhone settings, caption language, camera angle or Bolna stream timing actually behave. The parent technical tracks own those findings.

## 3. Which direction should lead, and what would make it competitively credible?

### Takeaway
Lead with the ordinary-call product, but separate the best story from the easiest physical demo. A pickup conversation has the clearest researched everyday barrier; a familiar-business appointment call offers a calmer camera setup. If that route fails a short engineering gate, the preferred pivot is a face-to-face service-counter bridge. Do not begin with a generalized autonomous assistant, a universal ISL translator, or multiple half-built modes.

### Cited Findings
- The impact basis is communication access and agency, not proven total addressable market or an official hackathon scoring weight. The source base establishes real barriers and alternatives, not the probability of winning. — [NAD India](https://nadindia.org/Projects/Accessibility); [Indian study](https://roshni-poddar.github.io/assets/pdf/interact23a-sub1087-cam-i7.pdf)
- Existing VRI/VRS establishes prior art for the interface concept. WFD's current guidance makes community involvement and transparent performance material to credibility. — [SignAble](https://signable.live/for-individuals-communicate-with-the-deaf/); [WFD 2025](https://wfdeaf.org/artificial-intelligence-and-sign-languages/)

### Inferences

The following comparison is **our engineering/product judgment**, not an official judging rubric. “Potential” assumes the bounded workflow actually works; every option still depends on unproven sign input. No numeric score implies measured user preference.

| Direction | Impact potential | Bolna fit | Seamlessness | Near-term feasibility | Distinctiveness |
|---|---|---|---|---|---|
| A: own-call pickup | High for a concrete access barrier | Medium, conditional speech/session integration | High caller workflow fidelity; difficult physical posture | Medium-low outdoors; easier staged indoors | High if correction works in the existing call |
| B: face-to-face counter | High for routine administrative access | High if Bolna handles both local spoken turns and signed inputs | High business workflow fidelity; user opens/props phone | Medium; fewer unrelated-call restrictions | Medium; must beat a caption/phrase-board demo |
| C: own-call appointment | High agency; bounded administrative outcome | Medium, conditional outgoing-only role | High call fidelity; app switch and position required | Medium-low until device/language gate passes | High if recognizer supports genuine negotiation |
| D: delegated appointment | Potentially high convenience; different agency model | High; Bolna carries out the voice task | Medium; user delegates instead of conversing | Medium if supervised escalation is supported | Medium-low without unusually good accessible supervision |
| E: app-owned live relay | High communication scope potential | High; actual media/session ownership | Medium; new calling workflow and identity | Medium; more system control but telephony work | Medium; established VRS/caption-call competition |

**Recommended ordering:** conditional A/C as one ordinary-call product family → B as the fallback product → D only if explicit delegation is acceptable → E if incoming-language/context control outweighs the original calling experience. Do not implement A and C separately; use one to choose the first dialogue/phrase set. Selection should depend on whether we can provide suitable licensed sign examples and a credible physical demonstration.

**The strongest counterargument to the recommendation:** A/C make Bolna less central than a full voice-agent product and preserve an incoming-audio boundary that limits its reasoning. We should reject an architecturally redundant Bolna hop. The parent's discovery of a potential OSS text-input/audio-output session makes investigation justified, but only a real proof of faithful audio, turn order and useful language delivery would make that integration compelling.

**What to show judges, if built:** Start with a recognizable access failure; then show the complete conversation, including one unsupported/ambiguous input, a correction, and a successful concrete outcome. Display the exact supported scope. Separately show remote audio, latency distribution, wrong-spoken-utterance count, and signer-held-out evaluation where possible. These are suggested evidence dimensions, not fabricated results or acceptance thresholds.

**What to avoid:** A vocabulary count as the central result; reciting a memorized script with no meaningful response; adding Jev/Laya without measurable benefit; claiming captions equal ISL access; calling a provider bridge “your ordinary phone call”; claiming we replace interpreters or have validated all Deaf users.

**Near-term research/design deliverable:** One conversation map with normal, repair and refusal branches; exact source-qualified sign/phrase coverage; the spoken and readable languages; where the user supplies each fact; the actual Bolna role; and a decisive platform/session experiment. That provides a basis for a requirements document and tickets without authorizing product implementation today.

### Gaps
- No comparative usability evidence establishes that A, B or C is the preferred workflow. A hearing team's reenactment only tests engineering.
- The hackathon's mandatory Bolna condition is supplied by the founder; detailed judging weights remain unavailable. There is no defensible estimate of winning odds.
- A deaf-led review, even a short review of scope and demo script, would materially improve the submission's grounding, but no participant availability is assumed and no outreach was conducted.
