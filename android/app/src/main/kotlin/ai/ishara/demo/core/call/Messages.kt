package ai.ishara.demo.core.call

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

// Kotlin mirror of CallSession's Messages.swift / Vocabulary.swift (itself the mirror of
// backend/app/protocol.py). Wire keys are snake_case; every WebSocket message has a `type`.
// Swift does the real encoding and decoding on a call; these let Kotlin build server messages
// for local sessions, read outgoing app messages and exchange REST bodies with Swift.

/** JSON for the wire and for the Swift bridge's events. */
val CoreJson = Json {
    encodeDefaults = true
    explicitNulls = false
    ignoreUnknownKeys = true
    classDiscriminator = "type"
}

@Serializable
enum class CallState {
    @SerialName("dialing") DIALING,
    @SerialName("ringing") RINGING,
    @SerialName("in_call") IN_CALL,
    @SerialName("speaking") SPEAKING,
    @SerialName("ended") ENDED,
    @SerialName("error") ERROR,
}

@Serializable
enum class CaptionSpeaker {
    @SerialName("receptionist") RECEPTIONIST,
    @SerialName("agent") AGENT,
}

@Serializable
enum class DraftSource {
    @SerialName("llm") LLM,
    @SerialName("template") TEMPLATE,
}

@Serializable
enum class CallMode {
    @SerialName("live") LIVE,
    @SerialName("delegated") DELEGATED,
    @SerialName("steer") STEER,
}

@Serializable
enum class CallPurpose {
    @SerialName("doctor_appointment") DOCTOR_APPOINTMENT,
}

/** The backend's `Sign` literals, in its order. */
@Serializable
enum class Sign {
    @SerialName("hello") HELLO,
    @SerialName("thankyou") THANKYOU,
    @SerialName("yes") YES,
    @SerialName("no") NO,
    @SerialName("sorry") SORRY,
    @SerialName("doctor") DOCTOR,
    @SerialName("today") TODAY,
    @SerialName("tomorrow") TOMORROW,
    @SerialName("morning") MORNING,
    @SerialName("afternoon") AFTERNOON,
    @SerialName("evening") EVENING,
    @SerialName("time") TIME,
    @SerialName("please") PLEASE,
    @SerialName("now") NOW,
    @SerialName("wait") WAIT,
    @SerialName("night") NIGHT,
    @SerialName("yesterday") YESTERDAY,
    @SerialName("later") LATER,
    @SerialName("can") CAN,
    @SerialName("where") WHERE,
    @SerialName("who") WHO,
    @SerialName("why") WHY,
    @SerialName("have") HAVE,
    @SerialName("finish") FINISH,
    @SerialName("callonphone") CALLONPHONE,
    @SerialName("sick") SICK,
    @SerialName("hungry") HUNGRY,
    @SerialName("drink") DRINK,
    @SerialName("water") WATER,
    @SerialName("home") HOME,
    @SerialName("go") GO,
    @SerialName("see") SEE,
    @SerialName("hear") HEAR,
    @SerialName("read") READ,
}

@Serializable
enum class AskChoice {
    @SerialName("yes") YES,
    @SerialName("no") NO,
    @SerialName("wait") WAIT,
    @SerialName("tomorrow") TOMORROW,
    @SerialName("morning") MORNING,
    @SerialName("now") NOW,
}

@Serializable
data class AskOption(val choice: AskChoice, val spoken: String)

@Serializable
enum class ProposalOrigin {
    @SerialName("agent") AGENT,
    @SerialName("user") USER,
}

@Serializable
enum class ProposalOutcome {
    @SerialName("spoken") SPOKEN,
    @SerialName("held") HELD,
    @SerialName("cancelled") CANCELLED,
}

// MARK: REST

/** Body of `POST /calls`. Exactly one of [contactId] and [phoneNumber]. */
@Serializable
data class StartCallRequest(
    @SerialName("contact_id") val contactId: String? = null,
    @SerialName("phone_number") val phoneNumber: String? = null,
    val purpose: CallPurpose,
    val mode: CallMode = CallMode.LIVE,
    @SerialName("brief_id") val briefId: String? = null,
    val attended: Boolean = false,
)

/** Response of `POST /calls`. */
@Serializable
data class CallStart(
    @SerialName("call_id") val callId: String,
    val state: CallState,
    val mode: CallMode = CallMode.LIVE,
)

@Serializable
data class Detail(val label: String, val value: String)

@Serializable
data class Document(val name: String, val text: String)

/** [documents] is null rather than empty, so briefs without any keep the old JSON. */
@Serializable
data class Profile(
    val name: String,
    val callback: String? = null,
    val notes: String? = null,
    val details: List<Detail> = emptyList(),
    val documents: List<Document>? = null,
)

/** Body of `POST /briefs`. */
@Serializable
data class BriefRequest(
    val purpose: CallPurpose,
    val chips: List<Sign>,
    val profile: Profile,
    val request: String? = null,
)

/** Response of `POST /briefs`. */
@Serializable
data class Brief(
    @SerialName("brief_id") val briefId: String,
    val text: String,
    val goal: String,
    val constraints: List<String>,
)

@Serializable
data class TranscriptEntry(val speaker: CaptionSpeaker, val text: String, val at: Double)

/** Response of `GET /calls/{id}/notes`. */
@Serializable
data class CallNotes(
    @SerialName("call_id") val callId: String,
    val mode: CallMode,
    val ready: Boolean,
    val brief: String? = null,
    val outcome: String? = null,
    val summary: List<String> = emptyList(),
    @SerialName("open_questions") val openQuestions: List<String> = emptyList(),
    val transcript: List<TranscriptEntry> = emptyList(),
    @SerialName("bolna_summary") val bolnaSummary: String? = null,
    @SerialName("follow_ups") val followUps: List<String> = emptyList(),
    @SerialName("stepped_in") val steppedIn: Int = 0,
)

// MARK: App -> backend (WebSocket)

@Serializable
sealed interface AppMessage {
    @Serializable
    @SerialName("chips")
    data class Chips(@SerialName("turn_id") val turnId: String, val chips: List<Sign>) : AppMessage

    @Serializable
    @SerialName("approve")
    data class Approve(@SerialName("turn_id") val turnId: String, val text: String) : AppMessage

    @Serializable
    @SerialName("stop")
    data object Stop : AppMessage

    @Serializable
    @SerialName("end")
    data object End : AppMessage

    @Serializable
    @SerialName("answer")
    data class Answer(@SerialName("ask_id") val askId: String, val choice: AskChoice) : AppMessage

    @Serializable
    @SerialName("presence")
    data class Presence(val present: Boolean) : AppMessage

    @Serializable
    @SerialName("hold")
    data class Hold(@SerialName("turn_id") val turnId: String, val composing: Boolean) : AppMessage

    @Serializable
    @SerialName("say")
    data class Say(val text: String) : AppMessage
}

// MARK: Backend -> app (WebSocket)

@Serializable
sealed interface ServerMessage {
    @Serializable
    @SerialName("status")
    data class Status(val state: CallState) : ServerMessage

    /** `at` is unix time in seconds. */
    @Serializable
    @SerialName("caption")
    data class Caption(
        val text: String,
        val at: Double,
        val speaker: CaptionSpeaker = CaptionSpeaker.RECEPTIONIST,
    ) : ServerMessage

    @Serializable
    @SerialName("draft")
    data class Draft(@SerialName("turn_id") val turnId: String, val text: String, val source: DraftSource) : ServerMessage

    @Serializable
    @SerialName("spoken")
    data class Spoken(@SerialName("turn_id") val turnId: String) : ServerMessage

    @Serializable
    @SerialName("not_delivered")
    data class NotDelivered(@SerialName("turn_id") val turnId: String, val reason: String) : ServerMessage

    @Serializable
    @SerialName("error")
    data class Error(val code: String, val message: String) : ServerMessage

    @Serializable
    @SerialName("ask")
    data class Ask(
        @SerialName("ask_id") val askId: String,
        val question: String,
        val options: List<AskOption>,
        val fallback: String,
        @SerialName("timeout_s") val timeoutS: Double,
    ) : ServerMessage

    @Serializable
    @SerialName("ask_resolved")
    data class AskResolved(@SerialName("ask_id") val askId: String, val spoken: String, val source: String) : ServerMessage

    @Serializable
    @SerialName("proposal")
    data class Proposal(
        @SerialName("turn_id") val turnId: String,
        val text: String,
        @SerialName("window_s") val windowS: Double,
        val origin: ProposalOrigin = ProposalOrigin.AGENT,
    ) : ServerMessage

    @Serializable
    @SerialName("proposal_resolved")
    data class ProposalResolved(@SerialName("turn_id") val turnId: String, val outcome: ProposalOutcome) : ServerMessage

    @Serializable
    @SerialName("follow_up")
    data class FollowUp(val text: String) : ServerMessage
}
