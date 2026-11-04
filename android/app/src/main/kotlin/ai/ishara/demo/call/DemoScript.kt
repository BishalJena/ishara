package ai.ishara.demo.call

import ai.ishara.demo.core.call.DraftSource
import ai.ishara.demo.core.call.Sign
import ai.ishara.demo.recognition.RecognitionResult
import ai.ishara.demo.recognition.RecognitionResult.Recognised

/** The rehearsed clinic call from PLAN §1, used by [FakeCallDriver]. */
object DemoScript {
    data class Stage(
        /** What the receptionist says before the user replies (null for the opening turn). */
        val caption: String?,
        /** Show the red "can't see you" pill briefly before signing. */
        val losesFraming: Boolean,
        /** What the sign pipeline reports, in order. */
        val signs: List<RecognitionResult>,
    )

    /** The call agent's fixed lines, said without a SEND (backend/app/markers.py). */
    const val DISCLOSURE = "Hello, I'm calling for a Deaf caller who is using Ishara, a sign-language app. " +
        "Their replies may take a few seconds."
    const val GOODBYE = "Thank you for your time. Goodbye."

    val stages = listOf(
        // Turn 1: hello · doctor · tomorrow
        Stage(caption = null, losesFraming = false, signs = listOf(Recognised(Sign.HELLO), Recognised(Sign.DOCTOR), Recognised(Sign.TOMORROW))),
        // Turns 2–3b: "afternoon" is the planned wrong chip the user removes with ✕.
        Stage(
            caption = "We have 4 pm tomorrow. Does that work?",
            losesFraming = true,
            signs = listOf(Recognised(Sign.NO), Recognised(Sign.AFTERNOON), Recognised(Sign.MORNING)),
        ),
        // Turns 4–5: one unsure sign shows a red [?] chip that is never sent.
        Stage(
            caption = "Yes, 10:30 tomorrow morning.",
            losesFraming = false,
            signs = listOf(Recognised(Sign.YES), RecognitionResult.Unsure, Recognised(Sign.THANKYOU)),
        ),
    )

    /** Drafts the composer would return for the script's chip sets. */
    val composedDrafts = mapOf(
        listOf(Sign.HELLO, Sign.DOCTOR, Sign.TOMORROW) to "Hello, I'd like a doctor's appointment tomorrow.",
        listOf(Sign.NO, Sign.MORNING) to "No, sorry, 4 pm doesn't work. Is there anything tomorrow morning?",
        listOf(Sign.YES, Sign.THANKYOU) to "Yes, 10:30 tomorrow morning works. Thank you.",
    )

    /** Fixed fallback phrase per sign, joined in order, like the backend templates. */
    val templatePhrases = mapOf(
        Sign.HELLO to "Hello.",
        Sign.THANKYOU to "Thank you.",
        Sign.YES to "Yes.",
        Sign.NO to "No.",
        Sign.SORRY to "Sorry.",
        Sign.DOCTOR to "I'd like to see a doctor.",
        Sign.TODAY to "Today, please.",
        Sign.TOMORROW to "Tomorrow, please.",
        Sign.MORNING to "In the morning, please.",
        Sign.AFTERNOON to "In the afternoon, please.",
        Sign.EVENING to "In the evening, please.",
        Sign.TIME to "What time?",
        // ASL Signs glosses (D8), said plainly like backend/app/templates.py.
        Sign.PLEASE to "Please.",
        Sign.NOW to "Today, please.",
        Sign.WAIT to "A moment, please.",
        Sign.NIGHT to "At night, please.",
        Sign.YESTERDAY to "Yesterday.",
        Sign.LATER to "Maybe later.",
        Sign.CAN to "Can you help me with that?",
        Sign.WHERE to "Where is it?",
        Sign.WHO to "Who should I ask for?",
        Sign.WHY to "Why is that?",
        Sign.HAVE to "Do you have that?",
        Sign.FINISH to "That's all from me.",
        Sign.CALLONPHONE to "Please call me on the phone.",
        Sign.SICK to "I'm feeling sick.",
        Sign.HUNGRY to "I'm hungry.",
        Sign.DRINK to "I'd like a drink.",
        Sign.WATER to "Some water, please.",
        Sign.HOME to "At home.",
        Sign.GO to "I need to go.",
        Sign.SEE to "I'd like to see them.",
        Sign.HEAR to "I hear you.",
        Sign.READ to "I'll read it.",
    )

    /** LLM wording when the chips match a scripted turn, otherwise the template. */
    fun draft(signs: List<Sign>): Pair<String, DraftSource> {
        composedDrafts[signs]?.let { return it to DraftSource.LLM }
        val text = signs.joinToString(" ") { sign ->
            templatePhrases[sign] ?: (sign.wire.replaceFirstChar(Char::uppercase) + ".")
        }
        return text to DraftSource.TEMPLATE
    }
}
