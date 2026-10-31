package ai.ishara.demo.recognition.landmarks

/**
 * Decision D8: the landmark layout of the Kaggle "ASL Signs" competition, which the public
 * 1st-place model takes as input. Per frame 543 points × (x, y, z), in this order: face mesh
 * (468), left hand (21), pose (33), right hand (21). A part that was not detected is NaN, as in
 * the competition data. Port of SignPipeline's `KaggleLayout` (and `kaggle_frame` in
 * spikes/recognition/asl_model.py).
 *
 * The Holistic Landmarker reports 478 face points (the legacy mesh plus 10 iris points); only the
 * first 468 belong to the layout.
 */
object KaggleLayout {
    const val FACE_POINTS = LandmarkFrame.MINIMUM_FACE_COUNT
    const val HAND_POINTS = LandmarkFrame.HAND_COUNT
    const val POSE_POINTS = LandmarkFrame.POSE_COUNT
    const val POINTS = FACE_POINTS + HAND_POINTS + POSE_POINTS + HAND_POINTS
    const val COORDINATES = 3
    const val VALUES_PER_FRAME = POINTS * COORDINATES

    /** Offsets of each part, in points. */
    object Offset {
        const val FACE = 0
        const val LEFT_HAND = FACE_POINTS
        const val POSE = FACE_POINTS + HAND_POINTS
        const val RIGHT_HAND = FACE_POINTS + HAND_POINTS + POSE_POINTS
    }

    /** `[frames.size, 543, 3]` flattened row-major. */
    fun values(frames: List<LandmarkFrame>): FloatArray {
        val values = FloatArray(frames.size * VALUES_PER_FRAME)
        var index = 0
        fun append(landmarks: List<Landmark>?, count: Int) {
            if (landmarks == null || landmarks.size < count) {
                values.fill(Float.NaN, index, index + count * COORDINATES)
                index += count * COORDINATES
                return
            }
            for (point in 0 until count) {
                val landmark = landmarks[point]
                values[index++] = landmark.x
                values[index++] = landmark.y
                values[index++] = landmark.z
            }
        }
        for (frame in frames) {
            append(frame.face, FACE_POINTS)
            append(frame.leftHand, HAND_POINTS)
            append(frame.pose, POSE_POINTS)
            append(frame.rightHand, HAND_POINTS)
        }
        return values
    }
}

/** Maps a Kaggle-layout clip to the ASL Signs model's raw logits. */
fun interface LogitsModel {
    /**
     * [landmarks] is `frameCount × KaggleLayout.VALUES_PER_FRAME` values, NaN for missing parts.
     * Returns one raw logit per class, in the model's output order.
     */
    fun logits(landmarks: FloatArray, frameCount: Int): FloatArray
}
