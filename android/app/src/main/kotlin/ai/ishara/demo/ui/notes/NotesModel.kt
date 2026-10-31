package ai.ishara.demo.ui.notes

import ai.ishara.demo.call.CallDriver
import ai.ishara.demo.core.call.CallCoreException
import ai.ishara.demo.core.call.CallNotes
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlin.time.Duration
import kotlin.time.Duration.Companion.seconds

/**
 * Decision D9, last step: the call's notes (`GET /calls/{id}/notes`). The backend marks them
 * `ready` once the call has ended; Bolna's own summary can arrive a little later through its
 * webhook, so the app keeps checking for a short while, whether the notes screen is open or not.
 * Use it from the main thread.
 */
class NotesModel(
    val contactName: String,
    private val driver: CallDriver,
    /** Gets every set of notes loaded, so the saved call picks up Bolna's summary. */
    private val onNotes: (CallNotes) -> Unit = {},
    private val sleep: suspend (Duration) -> Unit = { delay(it) },
    private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate),
) {
    var notes: CallNotes? by mutableStateOf(null)
        private set

    var failure: String? by mutableStateOf(null)
        private set

    var isLoading: Boolean by mutableStateOf(false)
        private set

    private var polling: Job? = null

    /** Nothing more is expected: the call ended and Bolna's summary (if any) is in. */
    val isComplete: Boolean get() = notes?.let { it.ready && it.bolnaSummary != null } ?: false

    /**
     * Starts [run] once, owned by this model rather than a screen, so it goes on after the
     * notes screen closes. Later calls hand back the same job.
     */
    fun start(): Job = polling ?: scope.launch { run() }.also { polling = it }

    fun stop() {
        polling?.cancel()
    }

    /** Loads the notes, then refreshes until they are complete or the attempts run out. */
    suspend fun run() {
        for (attempt in 0..MAX_REFRESHES) {
            refresh()
            if (isComplete || attempt >= MAX_REFRESHES) return
            try {
                sleep(REFRESH_INTERVAL)
            } catch (e: CancellationException) {
                throw e
            } catch (_: Exception) {
                return
            }
        }
    }

    suspend fun refresh() {
        isLoading = true
        try {
            val loaded = driver.notes()
            notes = loaded
            failure = null
            onNotes(loaded)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            val status = (e as? CallCoreException)?.status
            failure = when {
                status == 404 -> "The backend no longer has this call (it may have restarted)."
                status != null -> "The notes couldn't be loaded (HTTP $status)."
                (e as? CallCoreException)?.kind == CallCoreException.Kind.NOT_HTTP_RESPONSE ->
                    "The backend couldn't be reached."
                else -> "The notes couldn't be loaded: ${e.message}"
            }
        } finally {
            isLoading = false
        }
    }

    companion object {
        val REFRESH_INTERVAL = 3.seconds
        const val MAX_REFRESHES = 10

        /** Plain words for the backend's outcome. */
        fun describe(outcome: String?, ready: Boolean): String {
            if (!ready) return "The call is still being wrapped up"
            return when (outcome) {
                "booked" -> "Booked"
                "callback" -> "The agent will need to call back"
                "declined" -> "Nothing suitable was offered"
                "no_answer" -> "Nobody answered"
                "done" -> "Finished"
                else -> "Not confirmed: read the transcript"
            }
        }
    }
}
