package ai.ishara.demo.models

import ai.ishara.demo.core.call.Document
import android.graphics.Bitmap
import java.util.UUID

/**
 * A photo or PDF the user attached to the steer request (iOS `Attachment`). Its text is read
 * on this phone and goes with the brief as a document, so Ishara can quote it (word for word,
 * only when asked). [problem] says why it can't be used; such an attachment sends nothing.
 */
data class Attachment(
    val name: String,
    val thumbnail: Bitmap?,
    val text: String,
    val problem: String? = null,
    val id: String = UUID.randomUUID().toString(),
) {
    val summary: String get() = problem ?: "Read on this phone · Ishara can quote it when asked"

    val document: Document? get() = if (problem == null) Document(name, text) else null

    companion object {
        /** iOS `AttachmentReader`'s cap on the text sent with the brief. */
        const val TEXT_LIMIT = 20_000
        const val UNREADABLE = "Couldn't open this file."
        const val NO_TEXT = "No text found in it."

        /** The text as it goes with the brief: trimmed and capped; none at all is a problem. */
        fun read(name: String, thumbnail: Bitmap?, text: String): Attachment {
            val kept = text.trim().take(TEXT_LIMIT)
            return Attachment(name, thumbnail, kept, problem = if (kept.isEmpty()) NO_TEXT else null)
        }

        fun unreadable(name: String): Attachment = Attachment(name, thumbnail = null, text = "", problem = UNREADABLE)
    }
}
