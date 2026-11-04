package ai.ishara.demo.recognition.pipeline

import ai.ishara.demo.recognition.CameraState
import ai.ishara.demo.recognition.GetReadyModel
import ai.ishara.demo.recognition.core.CalibrationError
import ai.ishara.demo.recognition.core.CalibrationException
import ai.ishara.demo.recognition.core.DetectorEvent
import ai.ishara.demo.recognition.core.DetectorFrame
import ai.ishara.demo.recognition.core.DetectorPoint
import ai.ishara.demo.recognition.core.RecognitionRules
import ai.ishara.demo.recognition.core.SignDetector
import ai.ishara.demo.recognition.landmarks.FrameSignals
import ai.ishara.demo.recognition.landmarks.LandmarkFrame

/**
 * The frame-by-frame logic between landmarks and the matcher, with no threads, camera or model,
 * so it can be tested with scripted landmark frames. Port of ios/Ishara/Recognition/RecognitionSession.swift.
 *
 * 1. Framing: ticks the Get ready checklist from what the tracker sees.
 * 2. Calibrating: once every check has passed, collects `calibrationS` of frames and asks
 *    [RecognitionRules.calibrate] for the rest line (retrying if it can't see the user).
 * 3. Detecting: feeds the detector, maps its status to the camera pill and hands back the
 *    landmark frames of every **accepted** segment. Rejected segments give nothing.
 *
 * Not thread-safe; [close] frees the detector.
 */
class RecognitionSession(private val rules: RecognitionRules) : AutoCloseable {
    /** One accepted sign, ready for [SegmentClassifier]. */
    data class SignClip(
        /** From the detector's start to its end: the frames the model reads. */
        val frames: List<LandmarkFrame>,
        /**
         * The rest frames after the end, up to the frame that made the detector end the sign
         * (about `endRestS`). Only the framing guard reads them (issue #58).
         */
        val restAfter: List<LandmarkFrame>,
        /** The calibrated rest line, so the framing guard can tell a resting hand from one that left. */
        val restY: Double,
    )

    sealed interface Output {
        data class Passed(val check: GetReadyModel.Check) : Output

        /** Seconds of calibration recording collected so far. */
        data class Calibrating(val seconds: Double) : Output

        /** The recording couldn't be used; calibration starts over. */
        data class CalibrationRestarted(val error: CalibrationError) : Output
        data class Calibrated(val restY: Double) : Output
        data class Camera(val state: CameraState) : Output

        /** One accepted sign. */
        data class Sign(val clip: SignClip) : Output
    }

    private sealed interface Phase {
        data object Framing : Phase
        data class Calibrating(val start: Double) : Phase
        data class Detecting(val detector: SignDetector) : Phase
    }

    private val params = rules.params
    private var phase: Phase = Phase.Framing
    private val passed = mutableSetOf<GetReadyModel.Check>()
    private val calibrationFrames = mutableListOf<DetectorFrame>()

    /** Recent frames, long enough to cover a whole sign plus pre-roll and the rest that ends it. */
    private val recent = ArrayDeque<LandmarkFrame>()

    val restY: Double? get() = (phase as? Phase.Detecting)?.detector?.restY

    fun process(frame: LandmarkFrame): List<Output> {
        val detectorFrame = detectorFrame(frame)
        when (val current = phase) {
            Phase.Framing -> {
                val newlyPassed = (checks(frame) - passed).sortedBy { it.name }
                passed += newlyPassed
                if (passed.size == GetReadyModel.Check.entries.size) {
                    phase = Phase.Calibrating(frame.timestamp)
                    calibrationFrames.clear()
                    calibrationFrames += detectorFrame
                }
                return newlyPassed.map(Output::Passed)
            }

            is Phase.Calibrating -> {
                calibrationFrames += detectorFrame
                val seconds = frame.timestamp - current.start
                if (seconds < params.calibrationS) return listOf(Output.Calibrating(seconds))
                return try {
                    val restY = rules.calibrate(calibrationFrames.toList())
                    phase = Phase.Detecting(rules.detector(restY))
                    calibrationFrames.clear()
                    listOf(Output.Calibrating(seconds), Output.Calibrated(restY))
                } catch (error: CalibrationException) {
                    phase = Phase.Calibrating(frame.timestamp)
                    calibrationFrames.clear()
                    calibrationFrames += detectorFrame
                    listOf(Output.CalibrationRestarted(error.error))
                }
            }

            is Phase.Detecting -> {
                remember(frame)
                return current.detector.update(detectorFrame).mapNotNull { output(it, current.detector.restY) }
            }
        }
    }

    override fun close() {
        (phase as? Phase.Detecting)?.detector?.close()
        phase = Phase.Framing
    }

    private fun remember(frame: LandmarkFrame) {
        recent.addLast(frame)
        val horizon = params.maxSignS + params.preRollS + params.endRestS + 1
        while (recent.first().timestamp < frame.timestamp - horizon) recent.removeFirst()
    }

    private fun output(event: DetectorEvent, restY: Double): Output? = when (event) {
        is DetectorEvent.Status -> Output.Camera(event.state)
        is DetectorEvent.Cut -> {
            val segment = event.segment
            if (!segment.accepted) {
                null
            } else {
                val frames = recent.filter { segment.start <= it.timestamp && it.timestamp <= segment.end }
                val restAfter = recent.filter { it.timestamp > segment.end }
                Output.Sign(SignClip(frames, restAfter, restY))
            }
        }
    }

    companion object {
        /**
         * No light meter: "Good light" passes once the tracker finds both shoulders, i.e. the
         * picture is good enough to track.
         */
        fun checks(frame: LandmarkFrame): Set<GetReadyModel.Check> = buildSet {
            if (frame.face != null) add(GetReadyModel.Check.FACE)
            if (frame.leftHand != null && frame.rightHand != null) add(GetReadyModel.Check.BOTH_HANDS)
            if (frame.hasTrackedShoulders) add(GetReadyModel.Check.LIGHT)
        }

        fun detectorFrame(frame: LandmarkFrame): DetectorFrame {
            val signals = FrameSignals(frame)
            val wrists = listOfNotNull(signals.leftWrist, signals.rightWrist).map { DetectorPoint(it.x.toDouble(), it.y.toDouble()) }
            return DetectorFrame(signals.timestamp, signals.body, wrists)
        }
    }
}
