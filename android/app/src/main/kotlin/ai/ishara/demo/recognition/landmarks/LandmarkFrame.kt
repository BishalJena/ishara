package ai.ishara.demo.recognition.landmarks

import ai.ishara.demo.recognition.NormalizedPoint

// Port of ios/Packages/SignPipeline/Sources/SignPipeline/Landmarks (LandmarkFrame, FrameSignals,
// HolisticLandmarks): the landmark types the ASL path needs. The legacy SignCLIP features are not ported.

/**
 * One landmark in normalized image coordinates, as MediaPipe reports it: [x] and [y] in 0..1 of
 * the upright image with y down, [z] depth on roughly the scale of x. Only pose landmarks carry
 * a [visibility].
 */
data class Landmark(val x: Float, val y: Float, val z: Float, val visibility: Float? = null) {
    /** Confidence as pose-format reads it: a pose landmark without a score still counts as detected. */
    val poseConfidence: Float get() = visibility ?: 1f
}

/** Pixel size of the upright image the landmarks were detected in. */
data class ImageSize(val width: Int, val height: Int)

enum class BodyPart { POSE, FACE, LEFT_HAND, RIGHT_HAND }

sealed class LandmarkFrameException(message: String) : IllegalArgumentException(message) {
    data class InvalidImageSize(val size: ImageSize) : LandmarkFrameException("invalid image size $size")
    data class UnexpectedLandmarkCount(val part: BodyPart, val count: Int) :
        LandmarkFrameException("unexpected $part landmark count $count")
    data class NonFiniteLandmark(val part: BodyPart) : LandmarkFrameException("non-finite $part landmark")
}

/**
 * Holistic landmarks for one video frame; a null part was not detected. Build it with [create],
 * which validates the counts (pose 33, face ≥ 468, hands 21) and that every coordinate is finite.
 */
@ConsistentCopyVisibility
data class LandmarkFrame private constructor(
    /** Presentation time of the source frame, in seconds. */
    val timestamp: Double,
    val imageSize: ImageSize,
    val pose: List<Landmark>?,
    val face: List<Landmark>?,
    /** The signer's left hand, as assigned by the Holistic graph. */
    val leftHand: List<Landmark>?,
    val rightHand: List<Landmark>?,
) {
    /** Both shoulders have pose confidence ≥ 0.5. */
    val hasTrackedShoulders: Boolean
        get() = pose != null && listOf(Pose.LEFT_SHOULDER, Pose.RIGHT_SHOULDER).all {
            pose[it].poseConfidence >= MINIMUM_TRACKED_SHOULDER_VISIBILITY
        }

    /** The same landmarks at another time (held frames between replayed clips). */
    fun at(timestamp: Double): LandmarkFrame = copy(timestamp = timestamp)

    /** A validated copy with some parts replaced. */
    fun with(
        pose: List<Landmark>? = this.pose,
        face: List<Landmark>? = this.face,
        leftHand: List<Landmark>? = this.leftHand,
        rightHand: List<Landmark>? = this.rightHand,
    ): LandmarkFrame = create(timestamp, imageSize, pose, face, leftHand, rightHand)

    object Pose {
        const val LEFT_SHOULDER = 11
        const val RIGHT_SHOULDER = 12
        /** MediaPipe pose wrists, matching the Holistic hands: 15 is the left wrist, 16 the right. */
        const val LEFT_WRIST = 15
        const val RIGHT_WRIST = 16
    }

    companion object {
        const val POSE_COUNT = 33

        /** Legacy Holistic face mesh size; the Holistic Landmarker adds 10 iris points. */
        const val MINIMUM_FACE_COUNT = 468
        const val HAND_COUNT = 21

        /** Hand landmark 0. */
        const val WRIST_INDEX = 0
        const val MINIMUM_TRACKED_SHOULDER_VISIBILITY = 0.5f

        fun create(
            timestamp: Double,
            imageSize: ImageSize,
            pose: List<Landmark>? = null,
            face: List<Landmark>? = null,
            leftHand: List<Landmark>? = null,
            rightHand: List<Landmark>? = null,
        ): LandmarkFrame {
            if (imageSize.width <= 0 || imageSize.height <= 0) throw LandmarkFrameException.InvalidImageSize(imageSize)
            check(pose, BodyPart.POSE) { it == POSE_COUNT }
            check(face, BodyPart.FACE) { it >= MINIMUM_FACE_COUNT }
            check(leftHand, BodyPart.LEFT_HAND) { it == HAND_COUNT }
            check(rightHand, BodyPart.RIGHT_HAND) { it == HAND_COUNT }
            return LandmarkFrame(timestamp, imageSize, pose, face, leftHand, rightHand)
        }

        /**
         * From MediaPipe Holistic Landmarker lists, which report an undetected part as an empty
         * list. Only pose landmarks keep their visibility.
         */
        fun holistic(
            timestamp: Double,
            imageSize: ImageSize,
            pose: List<Landmark>,
            face: List<Landmark>,
            leftHand: List<Landmark>,
            rightHand: List<Landmark>,
        ): LandmarkFrame {
            fun detected(landmarks: List<Landmark>, keepVisibility: Boolean): List<Landmark>? = when {
                landmarks.isEmpty() -> null
                keepVisibility -> landmarks
                else -> landmarks.map { it.copy(visibility = null) }
            }
            return create(
                timestamp, imageSize,
                pose = detected(pose, keepVisibility = true),
                face = detected(face, keepVisibility = false),
                leftHand = detected(leftHand, keepVisibility = false),
                rightHand = detected(rightHand, keepVisibility = false),
            )
        }

        private fun check(landmarks: List<Landmark>?, part: BodyPart, isValid: (Int) -> Boolean) {
            if (landmarks == null) return
            if (!isValid(landmarks.size)) throw LandmarkFrameException.UnexpectedLandmarkCount(part, landmarks.size)
            if (!landmarks.all { it.x.isFinite() && it.y.isFinite() && it.z.isFinite() }) {
                throw LandmarkFrameException.NonFiniteLandmark(part)
            }
        }
    }
}

/** Per-frame cues for the start/stop detector. */
data class FrameSignals(
    val timestamp: Double,
    /** Both shoulders tracked (visibility ≥ 0.5). */
    val body: Boolean,
    /** Hand landmark 0 of the signer's left hand, when that hand is detected. */
    val leftWrist: NormalizedPoint?,
    val rightWrist: NormalizedPoint?,
) {
    constructor(frame: LandmarkFrame) : this(
        timestamp = frame.timestamp,
        body = frame.hasTrackedShoulders,
        leftWrist = frame.leftHand?.let(::wrist),
        rightWrist = frame.rightHand?.let(::wrist),
    )

    private companion object {
        fun wrist(hand: List<Landmark>): NormalizedPoint =
            hand[LandmarkFrame.WRIST_INDEX].let { NormalizedPoint(it.x, it.y) }
    }
}
