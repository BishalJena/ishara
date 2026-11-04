package ai.ishara.demo.call

import ai.ishara.demo.models.CallHistory
import ai.ishara.demo.ui.notes.NotesModel
import kotlinx.coroutines.delay
import kotlin.time.Duration

/**
 * What happens once a call is over, whatever screen is open: it is saved to Recent calls, and
 * a Call for me call's notes are followed until Bolna's summary is in (or the tries run out),
 * each change saved to the call. The follow-up keeps going when the user leaves the notes,
 * goes Home or starts another call; it only reads its own call's notes.
 *
 * Live calls aren't followed: the backend's notes for them hold only the transcript, never an
 * outcome or Bolna's summary, and the call screen's captions are saved already.
 */
object CallFollowUp {
    /** Saves the call and returns the notes being followed; null for a live call or one never placed. */
    fun callEnded(
        call: ActiveCallViewModel,
        history: CallHistory,
        sleep: suspend (Duration) -> Unit = { delay(it) },
    ): NotesModel? {
        val record = call.record ?: return null
        history.save(record)
        if (!call.isDelegated) return null
        val notes = NotesModel(
            contactName = record.contactName,
            driver = call.driver,
            onNotes = { history.update(record.id, it) },
            sleep = sleep,
        )
        notes.start()
        return notes
    }
}
