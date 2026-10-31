@file:OptIn(ExperimentalSerializationApi::class)

package ai.ishara.demo.core.call

import kotlinx.coroutines.flow.StateFlow
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonClassDiscriminator

/**
 * One call's state and the user's actions on it: a proxy for CallSession's `TurnStore`,
 * which enforces the SEND safety rules. Call the actions on the main thread.
 */
interface CallStore {
    val snapshot: StateFlow<CallSnapshot>

    /** Runs one `TurnStore` method; the result is its Bool return value, when it has one. */
    fun run(command: CallCommand): Boolean?

    /** False when the call is over or a recognised chip would exceed the chip limit. */
    fun add(chip: Chip): Boolean = run(CallCommand.Add(chip)) == true

    fun remove(chip: Chip) {
        run(CallCommand.Remove(chip.id))
    }

    fun useQuickReply(reply: QuickReply) {
        run(CallCommand.UseQuickReply(reply))
    }

    fun clear() {
        run(CallCommand.Clear)
    }

    /** Approves exactly the shown draft, once. */
    fun send() {
        run(CallCommand.Send)
    }

    fun resend() {
        run(CallCommand.Resend)
    }

    fun stop() {
        run(CallCommand.Stop)
    }

    fun end() {
        run(CallCommand.End)
    }

    fun setPresent(present: Boolean) {
        run(CallCommand.SetPresent(present))
    }

    fun approveProposal() {
        run(CallCommand.ApproveProposal)
    }

    fun startComposing() {
        run(CallCommand.StartComposing)
    }

    fun stopComposing() {
        run(CallCommand.StopComposing)
    }

    /** False when the call can't carry [text]. */
    fun say(text: String): Boolean = run(CallCommand.Say(text)) == true

    fun holdPreview() {
        run(CallCommand.HoldPreview)
    }

    /** False when there is no open question or [choice] isn't one of its options. */
    fun answer(choice: AskChoice): Boolean = run(CallCommand.Answer(choice)) == true

    /** True when [sign] answered the open question instead of becoming a chip. */
    fun answerIfAsked(sign: Sign): Boolean = run(CallCommand.AnswerIfAsked(sign)) == true

    fun connectionLost() {
        run(CallCommand.ConnectionLost)
    }
}

/** CallSession's quick replies; Swift owns their sentences. */
@Serializable
enum class QuickReply {
    @SerialName("yes") YES,
    @SerialName("no") NO,
    @SerialName("wait") WAIT,
    @SerialName("repeat") REPEAT,
}

/** The `command` JSON the Swift bridge takes (Call/CallCommand.swift): `{"op": <TurnStore method>, ...}`. */
@Serializable
@JsonClassDiscriminator("op")
sealed interface CallCommand {
    @Serializable
    @SerialName("add")
    data class Add(val chip: Chip) : CallCommand

    @Serializable
    @SerialName("remove")
    data class Remove(val chipId: String) : CallCommand

    @Serializable
    @SerialName("useQuickReply")
    data class UseQuickReply(val reply: QuickReply) : CallCommand

    @Serializable
    @SerialName("clear")
    data object Clear : CallCommand

    @Serializable
    @SerialName("send")
    data object Send : CallCommand

    @Serializable
    @SerialName("resend")
    data object Resend : CallCommand

    @Serializable
    @SerialName("stop")
    data object Stop : CallCommand

    @Serializable
    @SerialName("end")
    data object End : CallCommand

    @Serializable
    @SerialName("setPresent")
    data class SetPresent(val present: Boolean) : CallCommand

    @Serializable
    @SerialName("approveProposal")
    data object ApproveProposal : CallCommand

    @Serializable
    @SerialName("startComposing")
    data object StartComposing : CallCommand

    @Serializable
    @SerialName("stopComposing")
    data object StopComposing : CallCommand

    @Serializable
    @SerialName("say")
    data class Say(val text: String) : CallCommand

    @Serializable
    @SerialName("holdPreview")
    data object HoldPreview : CallCommand

    @Serializable
    @SerialName("answer")
    data class Answer(val choice: AskChoice) : CallCommand

    @Serializable
    @SerialName("answerIfAsked")
    data class AnswerIfAsked(val sign: Sign) : CallCommand

    @Serializable
    @SerialName("connectionLost")
    data object ConnectionLost : CallCommand
}
