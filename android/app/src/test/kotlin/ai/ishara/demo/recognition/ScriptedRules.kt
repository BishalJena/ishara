package ai.ishara.demo.recognition

import ai.ishara.demo.recognition.core.CalibrationError
import ai.ishara.demo.recognition.core.CalibrationException
import ai.ishara.demo.recognition.core.ClipQuality
import ai.ishara.demo.recognition.core.DetectorEvent
import ai.ishara.demo.recognition.core.DetectorFrame
import ai.ishara.demo.recognition.core.DetectorParams
import ai.ishara.demo.recognition.core.FramingFrame
import ai.ishara.demo.recognition.core.QualityFrame
import ai.ishara.demo.recognition.core.RecognitionRules
import ai.ishara.demo.recognition.core.Segment
import ai.ishara.demo.recognition.core.SignDetector
import kotlin.math.roundToLong

/** The shared spec's defaults (RecognitionCore's `DetectorParams()`), for JVM tests. */
val specParams = DetectorParams(
    calibrationS = 2.0, restMargin = 0.08, defaultRestY = 0.80, restYMin = 0.50, restYMax = 0.95,
    minBodyFraction = 0.8, startHoldS = 0.10, endRestS = 0.40, preRollS = 0.20, minSignS = 0.30,
    maxSignS = 4.0, lostBodyS = 0.50,
)

/**
 * RecognitionCore stand-in for JVM tests (the Swift library only runs on the device; the device
 * tests use the real one). Calibration answers [restY] or fails with [calibrationErrors] in turn;
 * the detector replays [events] at the frame times they are keyed by (milliseconds).
 */
class ScriptedRules(
    var restY: Double = Landmarks.CALIBRATED_REST_Y,
    val calibrationErrors: ArrayDeque<CalibrationError> = ArrayDeque(),
    val events: Map<Long, List<DetectorEvent>> = emptyMap(),
    var handLeft: Boolean = false,
    var quality: ClipQuality = ClipQuality(1.0, 1.0),
) : RecognitionRules {
    override val params = specParams
    val calibrations = mutableListOf<List<DetectorFrame>>()
    val detectorFrames = mutableListOf<DetectorFrame>()
    val framingCalls = mutableListOf<Pair<List<FramingFrame>, Double>>()
    val qualityCalls = mutableListOf<List<QualityFrame>>()
    var closedDetectors = 0
        private set

    override fun calibrate(frames: List<DetectorFrame>): Double {
        calibrations += frames
        calibrationErrors.removeFirstOrNull()?.let { throw CalibrationException(it) }
        return restY
    }

    override fun detector(restY: Double): SignDetector = object : SignDetector {
        override val restY = restY

        override fun update(frame: DetectorFrame): List<DetectorEvent> {
            detectorFrames += frame
            return events[ms(frame.t)].orEmpty()
        }

        override fun close() {
            closedDetectors++
        }
    }

    override fun handLeftFrame(frames: List<FramingFrame>, restY: Double): Boolean {
        framingCalls += frames to restY
        return handLeft
    }

    override fun quality(frames: List<QualityFrame>): ClipQuality {
        qualityCalls += frames
        return quality
    }

    companion object {
        fun ms(t: Double) = (t * 1000).roundToLong()

        fun status(state: CameraState) = DetectorEvent.Status(state)

        fun cut(start: Double, end: Double, reason: String? = null) = DetectorEvent.Cut(Segment(start, end, reason))
    }
}
