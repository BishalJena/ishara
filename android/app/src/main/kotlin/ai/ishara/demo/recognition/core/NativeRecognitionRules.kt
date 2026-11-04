package ai.ishara.demo.recognition.core

import ai.ishara.demo.recognition.CameraState
import kotlinx.serialization.Serializable
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

internal val RecognitionJson = Json {
    explicitNulls = false
}

/** [RecognitionRules] backed by RecognitionCore in `libIsharaCore.so`. */
class NativeRecognitionRules(override val params: DetectorParams = defaultParams) : RecognitionRules {
    private val paramsJson = RecognitionJson.encodeToString(params)

    override fun calibrate(frames: List<DetectorFrame>): Double {
        val output = RecognitionJson.decodeFromString<CalibrationWire>(
            RecognitionNative.calibrate(RecognitionJson.encodeToString(frames.map(::DetectorFrameWire)), paramsJson),
        )
        output.error?.let { wire ->
            throw CalibrationException(CalibrationError.entries.first { it.wire == wire })
        }
        return checkNotNull(output.restY) { "calibration gave neither a rest line nor an error" }
    }

    override fun detector(restY: Double): SignDetector = NativeSignDetector(restY, paramsJson)

    override fun handLeftFrame(frames: List<FramingFrame>, restY: Double): Boolean =
        RecognitionNative.handLeftFrame(RecognitionJson.encodeToString(ListSerializer(FramingFrame.serializer()), frames), restY)

    override fun quality(frames: List<QualityFrame>): ClipQuality {
        val wire = RecognitionJson.encodeToString(frames.map { QualityFrameWire(it.body, it.handCount) })
        val output = RecognitionJson.decodeFromString<QualityWire>(RecognitionNative.clipQuality(wire))
        return ClipQuality(output.poseFraction, output.handFraction)
    }

    companion object {
        /** RecognitionCore's `DetectorParams()`, the shared spec defaults. */
        val defaultParams: DetectorParams by lazy {
            RecognitionJson.decodeFromString(RecognitionNative.defaultDetectorParams())
        }
    }
}

private class NativeSignDetector(override val restY: Double, paramsJson: String) : SignDetector {
    private var handle = RecognitionNative.createDetector(restY, paramsJson)

    override fun update(frame: DetectorFrame): List<DetectorEvent> {
        check(handle != 0L) { "detector closed" }
        val wrists = DoubleArray(frame.wrists.size * 2)
        frame.wrists.forEachIndexed { index, point ->
            wrists[index * 2] = point.x
            wrists[index * 2 + 1] = point.y
        }
        val json = RecognitionNative.detectorUpdate(handle, frame.t, frame.body, wrists)
        return RecognitionJson.decodeFromString<List<DetectorEventWire>>(json).map(DetectorEventWire::event)
    }

    override fun close() {
        if (handle != 0L) RecognitionNative.freeDetector(handle)
        handle = 0
    }
}

@Serializable
private data class DetectorFrameWire(val t: Double, val body: Boolean, val wrists: List<List<Double>>) {
    constructor(frame: DetectorFrame) : this(frame.t, frame.body, frame.wrists.map { listOf(it.x, it.y) })
}

@Serializable
private data class CalibrationWire(val restY: Double? = null, val error: String? = null)

@Serializable
private data class QualityFrameWire(val body: Boolean, val handCount: Int)

@Serializable
private data class QualityWire(val poseFraction: Double, val handFraction: Double)

@Serializable
private data class SegmentWire(val start: Double, val end: Double, val reason: String? = null)

@Serializable
private data class DetectorEventWire(val status: String? = null, val segment: SegmentWire? = null) {
    fun event(): DetectorEvent = when {
        segment != null -> DetectorEvent.Cut(Segment(segment.start, segment.end, segment.reason))
        status != null -> DetectorEvent.Status(cameraState(status))
        else -> error("detector event without status or segment")
    }

    private fun cameraState(status: String) = when (status) {
        "watching" -> CameraState.WATCHING
        "signing" -> CameraState.SIGNING
        "cant_see" -> CameraState.CANT_SEE
        else -> error("unknown detector status $status")
    }
}
