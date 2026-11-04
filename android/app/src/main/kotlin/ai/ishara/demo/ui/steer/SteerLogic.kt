package ai.ishara.demo.ui.steer

import ai.ishara.demo.call.ActiveCallViewModel
import ai.ishara.demo.call.ActiveCallViewModel.EndReason
import ai.ishara.demo.call.ActiveCallViewModel.Phase
import ai.ishara.demo.core.call.CallState
import ai.ishara.demo.core.call.Caption
import ai.ishara.demo.core.call.Proposal
import ai.ishara.demo.core.call.ProposalOrigin
import kotlin.math.max
import kotlin.math.roundToInt

/**
 * The lines Ishara says to the receptionist while the user types or signs (the backend's
 * FILLERS and LONG_WAIT_LINES in app/delegate.py). A run of them shows as its last line.
 */
object CoverLines {
    val all = setOf(
        "One moment, please.", "Just a second, let me check.", "Bear with me a moment.",
        "Let me confirm that.", "One moment, I'm checking.",
        "Thank you for waiting. Their reply is on its way.", "Sorry for the wait, they're still replying.",
    )

    /** [folded]: how many cover lines before this one were folded into it. */
    data class Row(val index: Int, val caption: Caption, val folded: Int)

    fun rows(captions: List<Caption>): List<Row> {
        fun isCover(i: Int) = captions[i].speaker == Caption.Speaker.AGENT && captions[i].text in all
        val rows = mutableListOf<Row>()
        var run = 0
        for (i in captions.indices) {
            if (isCover(i) && i + 1 < captions.size && isCover(i + 1)) {
                run += 1
                continue
            }
            rows += Row(i, captions[i], if (isCover(i)) run else 0)
            run = 0
        }
        return rows
    }
}

/** Days, clock times and amounts in the receptionist's words, as pinned facts. */
object CallFacts {
    enum class Kind { CLOCK, CALENDAR, MONEY }

    data class Fact(val text: String, val kind: Kind)

    private val patterns = listOf(
        Regex("""\b\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)\b""", RegexOption.IGNORE_CASE) to Kind.CLOCK,
        Regex("""\b\d{1,2}:\d{2}\b""", RegexOption.IGNORE_CASE) to Kind.CLOCK,
        Regex(
            """\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|tomorrow|today)\b(?:\s+(?:morning|afternoon|evening))?""",
            RegexOption.IGNORE_CASE,
        ) to Kind.CALENDAR,
        Regex("""(?:₹|Rs\.?\s?)\d[\d,]*""", RegexOption.IGNORE_CASE) to Kind.MONEY,
    )

    private val hours = mapOf(
        "one" to 1, "two" to 2, "three" to 3, "four" to 4, "five" to 5, "six" to 6, "seven" to 7, "eight" to 8,
        "nine" to 9, "ten" to 10, "eleven" to 11, "twelve" to 12,
    )
    private val minutes = mapOf("fifteen" to "15", "thirty" to "30", "forty five" to "45", "forty-five" to "45")
    private val spokenTime = Regex(
        """\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)(?:\s+(fifteen|thirty|forty[ -]five))?(\s*(?:o'clock|am|pm|a\.m\.|p\.m\.))?\b""",
        RegexOption.IGNORE_CASE,
    )

    /**
     * The live transcriber writes times in words ("four pm", "ten thirty am"); as digits they
     * match the clock patterns. Only words next to am/pm, o'clock or minutes change.
     */
    fun digitsForSpokenTimes(line: String): String {
        val result = StringBuilder(line)
        for (match in spokenTime.findAll(line).toList().asReversed()) {
            val hour = hours[match.groupValues[1].lowercase()] ?: continue
            val minute = match.groups[2]?.value?.lowercase()?.let(minutes::get)
            val suffix = match.groups[3]?.value
            if (minute == null && suffix == null) continue
            val clock = "$hour" + (minute?.let { ":$it" } ?: "")
            val tail = suffix?.let { if (it.lowercase().contains("o'clock")) "" else it } ?: ""
            result.replace(match.range.first, match.range.last + 1, clock + tail)
        }
        return result.toString()
    }

    fun extract(lines: List<String>): List<Fact> {
        val seen = mutableListOf<Fact>()
        for (line in lines.map(::digitsForSpokenTimes)) {
            // "10:30 am" is one fact, not also "10:30": a match inside an earlier one is skipped.
            val taken = mutableListOf<IntRange>()
            for ((pattern, kind) in patterns) {
                for (match in pattern.findAll(line)) {
                    if (taken.any { it.first <= match.range.last && match.range.first <= it.last }) continue
                    taken += match.range
                    val fact = Fact(match.value, kind)
                    if (fact !in seen) seen += fact
                }
            }
        }
        return seen.takeLast(6)
    }
}

/**
 * One-tap replies for the receptionist's last line: a time on offer gets yes/no; a question
 * gets a repeat; everything gets "hold on".
 */
object QuickSteerReply {
    fun suggestions(lastLine: String?): List<String> {
        val line = lastLine.orEmpty().lowercase()
        val replies = mutableListOf<String>()
        val times = CallFacts.extract(listOf(lastLine.orEmpty())).filter { it.kind != CallFacts.Kind.MONEY }
        // A clock time is the offer ("Thursday at 10:30 am" → 10:30 am); else the day.
        val time = times.lastOrNull { it.kind == CallFacts.Kind.CLOCK } ?: times.lastOrNull()
        if (time != null) {
            replies += listOf("Yes, ${time.text} works", "${time.text} doesn't work, anything else?")
        } else if ("?" in line) {
            replies += listOf("Yes", "No")
        }
        replies += listOf("Could you repeat that?", "One moment, please")
        return replies
    }
}

/** The steer call screen's words, worked out from the call's state. */
object SteerCallText {
    /** "Ishara says in 2 s · tap to edit" over the filling Send bar; [now] in epoch seconds. */
    fun proposalLabel(proposal: Proposal, now: Double): String {
        if (proposal.origin != ProposalOrigin.AGENT) return "Saying your line · tap to edit"
        val remaining = max(0.0, proposal.windowS * (1 - proposal.progress(now)))
        return "Ishara says in ${remaining.roundToInt()} s · tap to edit"
    }

    /** "01:12 · from Ishara's number" while connected; the disclosure otherwise. */
    fun timer(connectedAt: Double?, phase: Phase, now: Double): String {
        if (connectedAt == null || phase != Phase.Live) return "Calls come from Ishara's number"
        val seconds = max(0, (now - connectedAt).toInt())
        return "%02d:%02d · from Ishara's number".format(seconds / 60, seconds % 60)
    }

    fun status(model: ActiveCallViewModel, isSigning: Boolean): String = when (val phase = model.phase) {
        is Phase.Connecting -> if (phase.state == CallState.RINGING) "Ringing…" else "Calling…"
        is Phase.Interrupted -> phase.notice
        is Phase.Disconnected -> phase.reason
        is Phase.Ended -> when (val reason = phase.reason) {
            EndReason.UserEnded, EndReason.RemoteEnded -> "Call ended"
            EndReason.HangUpUnconfirmed -> "Ended; hang-up not confirmed"
            is EndReason.Failed -> reason.message
        }
        Phase.Live -> when {
            !model.isSteppingIn -> "Ishara is handling it — step in any time"
            isSigning -> "You're signing — Ishara waits for you"
            else -> "You're typing — Ishara is covering"
        }
    }

    /**
     * Why the call didn't get through, if it didn't: it never started, or ended with no
     * receptionist line heard.
     */
    fun notThrough(model: ActiveCallViewModel): String? {
        model.startFailure?.let { return it }
        val reason = (model.phase as? Phase.Ended)?.reason ?: return null
        if (reason is EndReason.Failed) return reason.message
        if (reason == EndReason.RemoteEnded && model.captions.none { it.speaker == Caption.Speaker.RECEPTIONIST }) {
            return "${model.setup.contact.name} didn't answer."
        }
        return null
    }
}
