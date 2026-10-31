package ai.ishara.demo.call

import ai.ishara.demo.core.call.AskChoice
import ai.ishara.demo.core.call.AskOption
import ai.ishara.demo.core.call.Brief
import ai.ishara.demo.core.call.BriefRequest
import ai.ishara.demo.core.call.CallMode
import ai.ishara.demo.core.call.CallNotes
import ai.ishara.demo.core.call.CallPurpose
import ai.ishara.demo.core.call.CaptionSpeaker
import ai.ishara.demo.core.call.Sign
import ai.ishara.demo.core.call.TranscriptEntry

/**
 * The scripted delegated call (D9) the fake driver plays, so "Call for me" can be clicked
 * through without a backend. The brief, the agent's lines and the notes follow
 * backend/app/delegate.py (`build_brief`, `RuleBrain`, `build_notes`) closely enough to show
 * the same screens; the real wording comes from the backend.
 */
object DelegatedDemo {
    const val PAUSE_LINE = "One moment, please."
    const val CALLBACK_LINE = "I'll need to check that and call back. Thank you."
    const val CLOSE_LINE = "That's all, thank you so much for your help."
    const val OFFER = "We have 10:30 tomorrow morning. Does that work?"
    const val PROPOSAL = "10:30 tomorrow"
    const val CONFIRMATION = "Great, you're booked for 10:30 tomorrow morning."
    const val DECLINED = "Then please call back when you know a better time."
    const val ASK_TIMEOUT = 10.0

    /** Version B: the receptionist asks "when?" without offering a time. */
    const val OPEN_QUESTION = "What time would you like to come in?"
    const val WAIT_LINE = "One moment, please, I'm checking."

    private val days = mapOf(Sign.TODAY to "today", Sign.NOW to "today", Sign.TOMORROW to "tomorrow", Sign.YESTERDAY to "yesterday")
    private val parts = mapOf(
        Sign.MORNING to "in the morning",
        Sign.AFTERNOON to "in the afternoon",
        Sign.EVENING to "in the evening",
        Sign.NIGHT to "at night",
    )

    fun goal(purpose: CallPurpose): String = when (purpose) {
        CallPurpose.DOCTOR_APPOINTMENT -> "book a doctor's appointment"
    }

    /** When the user wants it, from the time chips: "tomorrow in the morning". */
    fun `when`(chips: List<Sign>): String? {
        val words = (chips.mapNotNull(days::get) + chips.mapNotNull(parts::get)).distinct()
        return words.takeIf { it.isNotEmpty() }?.joinToString(" ")
    }

    fun brief(request: BriefRequest): Brief {
        val goal = goal(request.purpose)
        val name = request.profile.name.trim()
        val time = `when`(request.chips)
        val lines = mutableListOf("Call on behalf of $name, who is Deaf and uses the Ishara app, to $goal.")
        if (time != null) lines += "Preferred: $time."
        request.profile.notes?.takeIf { it.isNotEmpty() }?.let { lines += "Reason, if asked: $it" }
        val share = listOf("name ($name)") + if (request.profile.callback == null) emptyList() else listOf("callback number")
        lines += "May share: ${share.joinToString(", ")}."
        lines += "Will not agree to anything outside this brief; anything else comes back to you as a question."
        return Brief(
            briefId = "demo-brief",
            text = lines.joinToString(" "),
            goal = goal,
            constraints = time?.let { listOf("$PREFERRED_TIME$it") } ?: emptyList(),
        )
    }

    /** The brief's preferred time, from its "preferred time: …" constraint. */
    fun preferredTime(brief: Brief): String? =
        brief.constraints.firstOrNull { it.startsWith(PREFERRED_TIME) }?.removePrefix(PREFERRED_TIME)

    fun opening(name: String, goal: String, `when`: String?): String =
        "I'd like to $goal for $name" + (`when`?.let { ", $it." } ?: ".")

    val options = listOf(
        AskOption(AskChoice.YES, "Yes, $PROPOSAL works. Thank you."),
        AskOption(AskChoice.NO, "No, $PROPOSAL doesn't work, sorry. Is there another time?"),
        AskOption(AskChoice.WAIT, WAIT_LINE),
    )

    /** The answer to an open "when?", like the backend's `_time_line`. */
    fun timeLine(`when`: String): String =
        `when`.replaceFirstChar(Char::uppercase) + ", please. What times are available?"

    /** The time words the user can sign or tap for an open "when?" (backend `TIME_OPTIONS`). */
    val timeOptions = listOf(
        AskOption(AskChoice.TOMORROW, timeLine("tomorrow")),
        AskOption(AskChoice.MORNING, timeLine("in the morning")),
        AskOption(AskChoice.NOW, timeLine("today, as soon as possible")),
        AskOption(AskChoice.WAIT, WAIT_LINE),
    )

    /** What Bolna's own summary says about the demo call, once it has arrived. */
    fun automaticSummary(goal: String, name: String): String = "The agent called to $goal for $name."

    /** Notes from the transcript, quoting it, like the backend's deterministic notes. */
    fun notes(
        goal: String,
        name: String,
        brief: String,
        transcript: List<TranscriptEntry>,
        answers: List<String>,
        ready: Boolean,
    ): CallNotes {
        val summary = mutableListOf("Goal: $goal for $name.")
        val receptionist = transcript.filter { it.speaker == CaptionSpeaker.RECEPTIONIST }.map { it.text }
        if (OFFER in receptionist) summary += "They offered: \"$OFFER\""
        summary += answers.map { "You answered: \"$it\"" }
        if (CONFIRMATION in receptionist) summary += "They confirmed: \"$CONFIRMATION\""
        var outcome: String? = null
        val open = mutableListOf<String>()
        if (ready) {
            when {
                CONFIRMATION in receptionist -> outcome = "booked"
                transcript.any { it.speaker == CaptionSpeaker.AGENT && it.text == CALLBACK_LINE } -> {
                    outcome = "callback"
                    open += "The agent promised to call back. Decide on the offer and call again."
                }
                answers.any { it.startsWith("No") } -> outcome = "declined"
                else -> {
                    outcome = "unclear"
                    open += "The outcome was not confirmed."
                }
            }
        }
        return CallNotes(
            callId = "demo-call",
            mode = CallMode.DELEGATED,
            ready = ready,
            brief = brief,
            outcome = outcome,
            summary = summary,
            openQuestions = open,
            transcript = transcript,
            bolnaSummary = null,
        )
    }

    private const val PREFERRED_TIME = "preferred time: "
}
