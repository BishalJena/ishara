package ai.ishara.demo.core.call

/** Safe legacy projection while canonical notes are being prepared or recovery is unavailable. */
fun requestTitle(request: String?): String {
    var text = request.orEmpty().trim()
    if (text.startsWith("Call on behalf of ")) {
        text = if (text.contains("Request:")) text.substringAfter("Request:").trim()
        else text.substringAfter(", to ", text)
    }
    text = text.split(Regex("\\s+(?:Preferred:|Reason, if asked:|May share:|Will not agree)"), limit = 2).first()
    for (prefix in listOf("I would like to ", "I'd like to ", "I want to ", "Please ", "Can you ")) {
        if (text.startsWith(prefix, ignoreCase = true)) { text = text.drop(prefix.length); break }
    }
    val title = text.split(Regex("\\s+")).take(7).joinToString(" ").trim().trimEnd('.', '!', '?')
    return title.replaceFirstChar { it.uppercaseChar() }.ifEmpty { "Call summary" }
}

val CallNotes.summaryComplete: Boolean get() = ready && (presentation?.status == "ready" || outcome == "no_answer")
val CallNotes.summaryTitle: String get() = presentation?.title?.trim()?.takeIf { it.isNotEmpty() } ?: requestTitle(brief)
val CallNotes.summaryOverview: String get() = presentation?.overview?.trim()?.takeIf { it.isNotEmpty() } ?: when (outcome) {
    "booked" -> "The appointment was booked."
    "done" -> "The request was handled."
    "no_answer" -> "Nobody answered the call."
    "callback" -> "A follow-up is needed to finish the request."
    "declined" -> "No suitable offer was accepted."
    else -> "The call ended without a confirmed outcome."
}
