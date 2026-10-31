package ai.ishara.demo.recognition

import ai.ishara.demo.core.call.Sign
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.StateFlow

/** One recognition outcome for a finished sign. */
sealed interface RecognitionResult {
    /** The recognizer is confident: a chip. */
    data class Recognised(val sign: Sign) : RecognitionResult

    /**
     * D8 grey zone: a vocabulary sign the model is fairly but not fully sure of. Shown as a
     * "Did you mean …?" tile; it becomes a chip only when the user taps it.
     */
    data class Candidate(val sign: Sign) : RecognitionResult

    /** Something was signed but nothing matched well enough: a [?] chip, never spoken. */
    data object Unsure : RecognitionResult

    /** Like [Unsure], because a hand left the picture during the sign or as it ended. */
    data object HandLeftFrame : RecognitionResult

    companion object {
        const val UNSURE_OPTION = "?"
        const val FRAMING_OPTION = "frame"

        /** Replay spellings: a sign name, `?` (unsure), `name?` (candidate) or `frame`. */
        fun fromReplayOption(text: String): RecognitionResult? {
            val word = text.trim().lowercase()
            return when {
                word == UNSURE_OPTION -> Unsure
                word == FRAMING_OPTION -> HandLeftFrame
                word.endsWith("?") -> Sign.fromWire(word.dropLast(1))?.let(::Candidate)
                else -> Sign.fromWire(word)?.let(::Recognised)
            }
        }
    }
}

enum class CameraState {
    /** Hands at rest, ready for the next sign (green). */
    WATCHING,

    /** A sign is in progress (yellow). */
    SIGNING,

    /** Face or hands not visible (red). */
    CANT_SEE,
}

/** What the call screen hears from recognition while the user signs. */
sealed interface RecognitionEvent {
    data class Camera(val state: CameraState) : RecognitionEvent
    data class Result(val result: RecognitionResult) : RecognitionEvent
}

enum class CameraPermission { NOT_DETERMINED, GRANTED, DENIED }

/** A normalized (0..1) point in the upright, unmirrored image recognition reads, y down. */
data class NormalizedPoint(val x: Float, val y: Float)

/**
 * What the preview draws on the user: tracked shoulders and wrists, and the rest line found by
 * calibration. The preview is mirrored, so it maps these points onto its mirrored picture.
 */
data class BodyOverlay(
    val imageWidth: Int,
    val imageHeight: Int,
    val shoulders: List<NormalizedPoint> = emptyList(),
    val wrists: List<NormalizedPoint> = emptyList(),
    /** Wrists below this line count as resting. null until calibration has finished. */
    val restY: Double? = null,
)

/** The live front camera, when recognition watches it. */
interface LiveCamera {
    val permission: StateFlow<CameraPermission>

    /** The device has no usable front camera. */
    val isUnavailable: StateFlow<Boolean>

    /** Latest wrists, shoulders and rest line; null until a frame is tracked. */
    val overlay: StateFlow<BodyOverlay?>

    /**
     * The answer to the system camera prompt, or the current permission when the app returns
     * from Settings. Android shows the prompt only from an Activity, so the screens ask and
     * report here; recognition starts the camera once it is granted.
     */
    fun onPermissionResult(granted: Boolean)

    /** The mirrored preview of the frames recognition reads. Never starts the camera itself. */
    @Composable
    fun Preview(modifier: Modifier)
}

/**
 * The on-device recognizer as the screens see it, so the app can run with the real pipeline
 * (camera or replayed videos) or with a replay of fixed results.
 *
 * Get ready: [start] turns frames on; [getReady] reports the framing checklist and the 2 s
 * hands-at-rest calibration. Active call: [signingEvents] streams the camera pill and one result
 * per accepted sign. Rejected sign attempts produce nothing.
 */
interface RecognitionController {
    val getReady: GetReadyModel

    /** Why recognition can't run (no camera permission, missing model), if it can't. */
    val failure: StateFlow<String?>

    /** Something the user should know that doesn't stop recognition. */
    val notice: StateFlow<String?>

    /** The live front camera to preview; null for saved videos or replayed results. */
    val camera: LiveCamera?

    /** Things the user can replay by hand when there is no camera. */
    val replayOptions: List<String>

    fun start()

    /**
     * Results and pill changes from now on. Only one stream is live at a time; a new call
     * finishes the previous one, so a result can never reach an older call screen.
     */
    fun signingEvents(): Flow<RecognitionEvent>

    fun replay(option: String)

    fun stop()
}
