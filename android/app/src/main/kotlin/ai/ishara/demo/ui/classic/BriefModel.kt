package ai.ishara.demo.ui.classic

import ai.ishara.demo.call.CallDriver
import ai.ishara.demo.core.call.Brief
import ai.ishara.demo.core.call.BriefRequest
import ai.ishara.demo.core.call.CallCoreException
import ai.ishara.demo.core.call.Profile
import ai.ishara.demo.core.call.ProtocolLimits
import ai.ishara.demo.core.call.Sign
import ai.ishara.demo.models.CallSetup
import ai.ishara.demo.models.Delegation
import ai.ishara.demo.recognition.CameraState
import ai.ishara.demo.recognition.RecognitionController
import ai.ishara.demo.recognition.RecognitionEvent
import ai.ishara.demo.recognition.RecognitionResult
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.CancellationException

/**
 * Decision D9, step 1: the user signs (or taps) what they need, adds the details the agent
 * may share, reads the brief the backend builds from exactly that, and approves it once by
 * starting the call. Editing anything after the brief was built hides it until it is built
 * again, so the approved brief always matches what is on screen. Use it from the main thread.
 */
class BriefModel(
    val setup: CallSetup,
    val driver: CallDriver,
    val recognition: RecognitionController,
) {
    var name: String by mutableStateOf(setup.details.name)
    var callback: String by mutableStateOf("")
    var reason: String by mutableStateOf("")

    /** Stay on the call and answer the agent's questions; off = the agent calls back instead. */
    var attended: Boolean by mutableStateOf(true)

    var chips: List<Sign> by mutableStateOf(emptyList())
        private set
    var candidate: Sign? by mutableStateOf(null)
        private set
    var showsFramingHint: Boolean by mutableStateOf(false)
        private set

    /** The last sign was not recognised ("?"); cleared by the next sign or tap. */
    var lastSignUnsure: Boolean by mutableStateOf(false)
        private set
    var cameraState: CameraState by mutableStateOf(CameraState.WATCHING)
        private set
    var isPreparing: Boolean by mutableStateOf(false)
        private set
    var failure: String? by mutableStateOf(null)
        private set
    private var prepared: Pair<BriefRequest, Brief>? by mutableStateOf(null)

    val request: BriefRequest
        get() = BriefRequest(
            purpose = setup.purpose,
            chips = chips,
            profile = Profile(name = trimmed(name).orEmpty(), callback = trimmed(callback), notes = trimmed(reason)),
        )

    /** The brief for exactly what is on screen now, if it has been built. */
    val brief: Brief? get() = prepared?.takeIf { it.first == request }?.second

    val canPrepare: Boolean get() = trimmed(name) != null && !isPreparing

    /** The call to place once the user approves the brief shown. */
    val approvedSetup: CallSetup?
        get() {
            val brief = brief ?: return null
            return setup.copy(
                details = setup.details.copy(name = trimmed(name) ?: setup.details.name),
                delegation = Delegation(brief = brief, attended = attended),
            )
        }

    /** Turns recognition results into chips until the screen goes away. */
    suspend fun run() {
        recognition.signingEvents().collect(::handle)
    }

    fun handle(event: RecognitionEvent) {
        val result = when (event) {
            is RecognitionEvent.Camera -> {
                cameraState = event.state
                return
            }
            is RecognitionEvent.Result -> event.result
        }
        candidate = null
        showsFramingHint = false
        lastSignUnsure = false
        when (result) {
            is RecognitionResult.Recognised -> add(result.sign)
            is RecognitionResult.Candidate -> candidate = result.sign
            RecognitionResult.Unsure -> lastSignUnsure = true
            RecognitionResult.HandLeftFrame -> {
                lastSignUnsure = true
                showsFramingHint = true
            }
        }
    }

    fun add(sign: Sign) {
        lastSignUnsure = false
        if (sign in chips || chips.size >= ProtocolLimits.MAX_CHIPS) return
        chips = chips + sign
    }

    fun remove(sign: Sign) {
        chips = chips - sign
    }

    fun acceptCandidate() {
        val sign = candidate ?: return
        candidate = null
        add(sign)
    }

    fun dismissCandidate() {
        candidate = null
    }

    /** `POST /briefs` for what is on screen. Nothing is dialled. */
    suspend fun prepare() {
        if (!canPrepare) return
        val request = request
        isPreparing = true
        failure = null
        try {
            prepared = request to driver.createBrief(request)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            failure = describe(e)
        } finally {
            isPreparing = false
        }
    }

    companion object {
        /** Time words to tap when signing is not convenient (the brief only carries chips). */
        val suggestions = listOf(Sign.TODAY, Sign.TOMORROW, Sign.MORNING, Sign.AFTERNOON, Sign.EVENING, Sign.LATER)

        private fun trimmed(text: String): String? = text.trim().takeIf { it.isNotEmpty() }

        private fun describe(error: Exception): String {
            val core = error as? CallCoreException
            val status = core?.status
            return when {
                status == 401 -> "The app token was refused. Check the app configuration."
                status == 422 -> "The backend didn't accept these details. Check the name and callback number."
                status != null -> "The backend couldn't build the brief (HTTP $status)."
                core?.kind == CallCoreException.Kind.NOT_HTTP_RESPONSE -> "The backend couldn't be reached."
                else -> "The brief couldn't be built: ${error.message}"
            }
        }
    }
}
