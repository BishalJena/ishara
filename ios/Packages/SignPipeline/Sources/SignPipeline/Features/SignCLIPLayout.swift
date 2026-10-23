/// Point selection and order of a SignCLIP frame vector, as produced by
/// `demo_sign.preprocess_pose` at SignCLIP revision a819944 on a pose-format
/// 0.9.0 Holistic pose: pose (33), face contours (128), left hand (21),
/// right hand (21); each point flattened as x, y, z.
public enum SignCLIPLayout {
    /// Sorted unique indices of MediaPipe's `FACEMESH_CONTOURS`, hardcoded upstream
    /// as `FACEMESH_CONTOURS_POINTS` and equal to pose-format's own list.
    public static let faceContourIndices: [Int] = [
        0, 7, 10, 13, 14, 17, 21, 33, 37, 39, 40, 46, 52, 53, 54, 55, 58, 61, 63,
        65, 66, 67, 70, 78, 80, 81, 82, 84, 87, 88, 91, 93, 95, 103, 105, 107, 109,
        127, 132, 133, 136, 144, 145, 146, 148, 149, 150, 152, 153, 154, 155, 157, 158,
        159, 160, 161, 162, 163, 172, 173, 176, 178, 181, 185, 191, 234, 246, 249, 251,
        263, 267, 269, 270, 276, 282, 283, 284, 285, 288, 291, 293, 295, 296, 297, 300,
        308, 310, 311, 312, 314, 317, 318, 321, 323, 324, 332, 334, 336, 338, 356, 361,
        362, 365, 373, 374, 375, 377, 378, 379, 380, 381, 382, 384, 385, 386, 387, 388,
        389, 390, 397, 398, 400, 402, 405, 409, 415, 454, 466,
    ]

    public static let dimensions = 3
    public static let pointCount =
        LandmarkFrame.poseCount + faceContourIndices.count + 2 * LandmarkFrame.handCount
    /// 203 points × 3 = 609, the SignCLIP `input_dim`.
    public static let valuesPerFrame = pointCount * dimensions

    /// BlazePose indices (`POSE_LANDMARKS` order).
    public enum Pose {
        public static let leftShoulder = 11
        public static let rightShoulder = 12
        /// KNEE, ANKLE, HEEL and FOOT_INDEX on both sides, zeroed by `pose_hide_legs`.
        public static let legs = 25...32
    }

    /// Hand landmark 0.
    public static let wristIndex = 0
}
