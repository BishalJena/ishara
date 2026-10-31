package ai.ishara.demo.recognition.core

import ai.ishara.demo.recognition.CameraState
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * RecognitionCore's rules as the pipeline uses them: rest calibration, the start/stop detector,
 * the framing guard and clip quality. [NativeRecognitionRules] runs the shared Swift code; JVM
 * tests substitute scripted rules.
 */
interface RecognitionRules {
    val params: DetectorParams

    /** The rest line from the "hands at rest" recording. Throws [CalibrationException]. */
    fun calibrate(frames: List<DetectorFrame>): Double

    fun detector(restY: Double): SignDetector

    /** A hand that took part in the sign was out of the picture too long (`FramingGuard`). */
    fun handLeftFrame(frames: List<FramingFrame>, restY: Double): Boolean

    fun quality(frames: List<QualityFrame>): ClipQuality
}

/** RecognitionCore's `SignDetector`: feed it frames in time order. Close it when done. */
interface SignDetector : AutoCloseable {
    val restY: Double

    fun update(frame: DetectorFrame): List<DetectorEvent>
}

/** RecognitionCore's open-set `LogitsMatcher` over the bundle's full softmax. */
fun interface LogitsMatching {
    fun match(logits: FloatArray, quality: ClipQuality): LogitsMatch
}

/** Detector tuning, keyed on the wire by the shared spec's snake_case names. */
@Serializable
data class DetectorParams(
    @SerialName("calibration_s") val calibrationS: Double,
    @SerialName("rest_margin") val restMargin: Double,
    @SerialName("default_rest_y") val defaultRestY: Double,
    @SerialName("rest_y_min") val restYMin: Double,
    @SerialName("rest_y_max") val restYMax: Double,
    @SerialName("min_body_fraction") val minBodyFraction: Double,
    @SerialName("start_hold_s") val startHoldS: Double,
    @SerialName("end_rest_s") val endRestS: Double,
    @SerialName("pre_roll_s") val preRollS: Double,
    @SerialName("min_sign_s") val minSignS: Double,
    @SerialName("max_sign_s") val maxSignS: Double,
    @SerialName("lost_body_s") val lostBodyS: Double,
)

/** What the tracker saw in one frame: time, both shoulders tracked, and the detected wrists. */
data class DetectorFrame(val t: Double, val body: Boolean, val wrists: List<DetectorPoint> = emptyList())

/** A normalized image point (0..1, y down) as RecognitionCore reads it, in double precision. */
data class DetectorPoint(val x: Double, val y: Double)

data class Segment(val start: Double, val end: Double, val reason: String? = null) {
    val accepted: Boolean get() = reason == null
}

sealed interface DetectorEvent {
    data class Status(val state: CameraState) : DetectorEvent
    data class Cut(val segment: Segment) : DetectorEvent
}

enum class CalibrationError(val wire: String) {
    TOO_SHORT("too_short"),
    CANT_SEE("cant_see"),
}

class CalibrationException(val error: CalibrationError) : Exception("calibration failed: ${error.wire}")

data class ClipQuality(val poseFraction: Double, val handFraction: Double)

/** What the tracker found in one frame of a clip: both shoulders, and how many hands. */
data class QualityFrame(val body: Boolean, val handCount: Int)

@Serializable
data class FramingHand(val tracked: Boolean, val wristX: Float? = null, val wristY: Float? = null)

@Serializable
data class FramingFrame(val timestamp: Double, val left: FramingHand, val right: FramingHand)

@Serializable
data class LogitsCandidate(val gloss: String, val p: Double)

/** The matcher's decision. Labels are the backend's sign wire names. */
sealed interface LogitsMatch {
    val top: List<LogitsCandidate>

    data class Chip(val label: String, val p: Double, val margin: Double, override val top: List<LogitsCandidate>) : LogitsMatch
    data class PickOne(val label: String, val p: Double, val margin: Double, override val top: List<LogitsCandidate>) : LogitsMatch
    data class Unsure(val reason: String, override val top: List<LogitsCandidate>) : LogitsMatch
}
