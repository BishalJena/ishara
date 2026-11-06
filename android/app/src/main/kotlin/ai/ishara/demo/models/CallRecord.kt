package ai.ishara.demo.models

import ai.ishara.demo.core.call.Caption
import ai.ishara.demo.core.call.CallMode
import ai.ishara.demo.core.call.CallNotes
import ai.ishara.demo.core.call.requestTitle
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * One finished call as kept on this phone (Recent calls): only what the call and notes
 * screens showed. No phone numbers: the app never has the contact's, and the user's
 * callback number stays in the brief request, which is not kept. Dates are epoch seconds.
 */
@Serializable
data class CallRecord(
    /** Uppercase UUID, also the file name. */
    val id: String,
    val date: Double,
    val contactName: String,
    /** The number dialled, when the user typed or picked one, so Home can offer it again. */
    val contactNumber: String? = null,
    /** Live (the user signs every reply) or delegated (Call for me). */
    val mode: CallMode,
    val captions: List<Line>,
    /** The Call for me notes, once loaded; updated when Bolna's summary arrives later. */
    val notes: CallNotes? = null,
    val request: String? = null,
) {
    val displayTitle: String get() = notes?.presentation?.title?.trim()?.takeIf { it.isNotEmpty() }
        ?: requestTitle(request ?: notes?.brief)

    /** A caption from the call screen. `CaptionSpeaker` has no user, so it isn't reused. */
    @Serializable
    data class Line(val speaker: Speaker, val text: String, val at: Double) {
        constructor(caption: Caption) : this(
            speaker = when (caption.speaker) {
                Caption.Speaker.RECEPTIONIST -> Speaker.RECEPTIONIST
                Caption.Speaker.AGENT -> Speaker.AGENT
                Caption.Speaker.USER -> Speaker.USER
            },
            text = caption.text,
            at = caption.at,
        )

        @Serializable
        enum class Speaker {
            @SerialName("receptionist") RECEPTIONIST,
            @SerialName("agent") AGENT,
            @SerialName("user") USER,
        }
    }
}
