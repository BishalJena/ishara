@file:OptIn(ExperimentalSerializationApi::class)

package ai.ishara.demo.core.call

import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonClassDiscriminator

/**
 * Everything CallSession's `TurnStore` exposes, as the Swift bridge sends it after each
 * change (Call/Snapshot.swift). Dates are epoch seconds. [canSend], [canResend],
 * [unspokenText], [isStopRequested] and [recognisedSigns] are the store's derived values.
 */
@Serializable
data class CallSnapshot(
    val state: CallState,
    val connectedAt: Double? = null,
    val captions: List<Caption>,
    val currentTurnId: String,
    val chips: List<Chip>,
    val draft: Draft? = null,
    val sending: SendingPhase,
    val stopProgress: StopProgress,
    val lastError: ServerError? = null,
    val notice: String? = null,
    val openQuestion: OpenQuestion? = null,
    val proposal: Proposal? = null,
    val isComposing: Boolean,
    val followUps: List<String>,
    val steppedIn: Int,
    val canSend: Boolean,
    val canResend: Boolean,
    val unspokenText: String? = null,
    val isStopRequested: Boolean,
    val recognisedSigns: List<Sign>,
)

@Serializable
data class Caption(val text: String, val at: Double, val speaker: Speaker) {
    @Serializable
    enum class Speaker {
        @SerialName("receptionist") RECEPTIONIST,
        @SerialName("agent") AGENT,
        @SerialName("user") USER,
    }
}

/** A chip on the signing screen. [id] is an uppercase UUID, as Swift prints it. */
@Serializable
data class Chip(val id: String, val kind: ChipKind) {
    val sign: Sign? get() = (kind as? ChipKind.Recognised)?.sign

    companion object {
        fun recognised(sign: Sign) = Chip(newId(), ChipKind.Recognised(sign))

        fun unsure() = Chip(newId(), ChipKind.Unsure)

        private fun newId() = java.util.UUID.randomUUID().toString().uppercase()
    }
}

@Serializable
@JsonClassDiscriminator("kind")
sealed interface ChipKind {
    @Serializable
    @SerialName("recognised")
    data class Recognised(val sign: Sign) : ChipKind

    @Serializable
    @SerialName("unsure")
    data object Unsure : ChipKind
}

@Serializable
data class Draft(val text: String, val origin: Origin) {
    @Serializable
    enum class Origin {
        @SerialName("llm") LLM,
        @SerialName("template") TEMPLATE,
        @SerialName("quickReply") QUICK_REPLY,
    }
}

/** What happened to the last approved sentence. */
@Serializable
@JsonClassDiscriminator("kind")
sealed interface SendingPhase {
    @Serializable
    @SerialName("idle")
    data object Idle : SendingPhase

    @Serializable
    @SerialName("speaking")
    data class Speaking(val turnId: String, val text: String) : SendingPhase

    @Serializable
    @SerialName("delivered")
    data object Delivered : SendingPhase

    @Serializable
    @SerialName("deliveredDespiteStop")
    data object DeliveredDespiteStop : SendingPhase

    @Serializable
    @SerialName("notDelivered")
    data class NotDelivered(val text: String) : SendingPhase

    @Serializable
    @SerialName("stopped")
    data class Stopped(val text: String) : SendingPhase
}

@Serializable
enum class StopProgress {
    @SerialName("none") NONE,
    @SerialName("requested") REQUESTED,
    @SerialName("tooLate") TOO_LATE,
}

@Serializable
data class ServerError(val code: String, val message: String)

@Serializable
data class OpenQuestion(
    val askId: String,
    val question: String,
    val options: List<AskOption>,
    val fallback: String,
    val timeoutS: Double,
    val askedAt: Double,
)

@Serializable
data class Proposal(
    val turnId: String,
    val text: String,
    val windowS: Double,
    val origin: ProposalOrigin,
    val shownAt: Double,
)
