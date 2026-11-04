package ai.ishara.demo.recognition.pipeline

import ai.ishara.demo.recognition.landmarks.ImageSize
import ai.ishara.demo.recognition.landmarks.Landmark
import ai.ishara.demo.recognition.landmarks.LandmarkFrame
import android.content.Context
import com.google.mediapipe.framework.image.BitmapImageBuilder
import com.google.mediapipe.tasks.components.containers.NormalizedLandmark
import com.google.mediapipe.tasks.core.BaseOptions
import com.google.mediapipe.tasks.core.Delegate
import com.google.mediapipe.tasks.vision.core.RunningMode
import com.google.mediapipe.tasks.vision.holisticlandmarker.HolisticLandmarker
import kotlin.math.roundToLong

/**
 * [LandmarkProvider] backed by MediaPipe's Holistic Landmarker in video mode, on the CPU, with the
 * task defaults (0.5) for every confidence, as on iOS. Video mode runs synchronously on the
 * caller's thread and needs strictly increasing millisecond timestamps. Frames must already be
 * upright: the Holistic task takes no rotation.
 */
class HolisticLandmarkProvider(context: Context, modelAssetPath: String) : LandmarkProvider, AutoCloseable {
    private val landmarker: HolisticLandmarker = HolisticLandmarker.createFromOptions(
        context,
        HolisticLandmarker.HolisticLandmarkerOptions.builder()
            .setBaseOptions(BaseOptions.builder().setModelAssetPath(modelAssetPath).setDelegate(Delegate.CPU).build())
            .setRunningMode(RunningMode.VIDEO)
            .setMinPoseDetectionConfidence(MIN_CONFIDENCE)
            .setMinPosePresenceConfidence(MIN_CONFIDENCE)
            .setMinFaceDetectionConfidence(MIN_CONFIDENCE)
            .setMinFacePresenceConfidence(MIN_CONFIDENCE)
            .setMinHandLandmarksConfidence(MIN_CONFIDENCE)
            .setOutputFaceBlendshapes(false)
            .setOutputPoseSegmentationMasks(false)
            .build(),
    )
    private var lastMilliseconds: Long? = null

    override fun landmarks(frame: VideoFrame): LandmarkFrame {
        val milliseconds = (frame.timestamp * 1000).roundToLong()
        lastMilliseconds?.let { last ->
            if (milliseconds <= last) throw NonIncreasingTimestampException(milliseconds, last)
        }
        lastMilliseconds = milliseconds
        val bitmap = frame.bitmap
        val result = landmarker.detectForVideo(BitmapImageBuilder(bitmap).build(), milliseconds)
        return LandmarkFrame.holistic(
            timestamp = frame.timestamp,
            imageSize = ImageSize(bitmap.width, bitmap.height),
            pose = result.poseLandmarks().map { landmark(it, it.visibility().orElse(null)) },
            face = result.faceLandmarks().map { landmark(it) },
            leftHand = result.leftHandLandmarks().map { landmark(it) },
            rightHand = result.rightHandLandmarks().map { landmark(it) },
        )
    }

    override fun close() = landmarker.close()

    private fun landmark(point: NormalizedLandmark, visibility: Float? = null) =
        Landmark(point.x(), point.y(), point.z(), visibility)

    class NonIncreasingTimestampException(val milliseconds: Long, val previous: Long) :
        IllegalArgumentException("timestamp $milliseconds ms is not after $previous ms")

    companion object {
        const val MODEL_ASSET = "holistic_landmarker.task"
        private const val MIN_CONFIDENCE = 0.5f
    }
}
