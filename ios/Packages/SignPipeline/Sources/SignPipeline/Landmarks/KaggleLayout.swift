/// Decision D8: the landmark layout of the Kaggle "ASL Signs" competition, which the public
/// 1st-place model takes as input. Per frame 543 points × (x, y, z), in this order: face mesh
/// (468), left hand (21), pose (33), right hand (21). A part that was not detected is NaN, as
/// in the competition data. Mirrors `kaggle_frame` in spikes/recognition/asl_model.py.
///
/// The Holistic Landmarker reports 478 face points (the legacy mesh plus 10 iris points);
/// only the first 468 belong to the layout.
public enum KaggleLayout {
    public static let facePoints = LandmarkFrame.minimumFaceCount
    public static let handPoints = LandmarkFrame.handCount
    public static let posePoints = LandmarkFrame.poseCount
    public static let points = facePoints + handPoints + posePoints + handPoints
    public static let coordinates = 3
    public static let valuesPerFrame = points * coordinates

    /// Offsets of each part, in points.
    public enum Offset {
        public static let face = 0
        public static let leftHand = facePoints
        public static let pose = facePoints + handPoints
        public static let rightHand = facePoints + handPoints + posePoints
    }

    /// `[frames.count, 543, 3]` flattened row-major.
    public static func values(for frames: [LandmarkFrame]) -> [Float] {
        var values = [Float]()
        values.reserveCapacity(frames.count * valuesPerFrame)
        for frame in frames {
            append(frame.face, count: facePoints, to: &values)
            append(frame.leftHand, count: handPoints, to: &values)
            append(frame.pose, count: posePoints, to: &values)
            append(frame.rightHand, count: handPoints, to: &values)
        }
        return values
    }

    private static func append(_ landmarks: [Landmark]?, count: Int, to values: inout [Float]) {
        guard let landmarks, landmarks.count >= count else {
            values.append(contentsOf: repeatElement(.nan, count: count * coordinates))
            return
        }
        for point in landmarks.prefix(count) {
            values.append(point.x)
            values.append(point.y)
            values.append(point.z)
        }
    }
}

/// Anything that maps a Kaggle-layout clip to the ASL Signs model's raw logits.
/// `LiteRTLogitsModel` (SignPipelineLiteRT) is the production implementation.
public protocol LogitsModel {
    /// - Parameters:
    ///   - landmarks: `frameCount × KaggleLayout.valuesPerFrame` values, NaN for missing parts.
    /// - Returns: one raw logit per class, in the model's output order.
    func logits(landmarks: [Float], frameCount: Int) throws -> [Float]
}
