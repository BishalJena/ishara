extension LandmarkFrame {
    /// Builds a frame from MediaPipe Holistic Landmarker lists, which report an
    /// undetected part as an empty list. Only pose landmarks keep their
    /// visibility: SignCLIP assembly treats every detected face and hand point
    /// as confidence 1, and the task's per-point hand scores are not used.
    public static func holistic(
        timestamp: Double,
        imageSize: ImageSize,
        pose: [Landmark],
        face: [Landmark],
        leftHand: [Landmark],
        rightHand: [Landmark]
    ) throws -> LandmarkFrame {
        func detected(_ landmarks: [Landmark], keepVisibility: Bool) -> [Landmark]? {
            guard !landmarks.isEmpty else { return nil }
            guard !keepVisibility else { return landmarks }
            return landmarks.map { Landmark(x: $0.x, y: $0.y, z: $0.z) }
        }
        return try LandmarkFrame(
            timestamp: timestamp,
            imageSize: imageSize,
            pose: detected(pose, keepVisibility: true),
            face: detected(face, keepVisibility: false),
            leftHand: detected(leftHand, keepVisibility: false),
            rightHand: detected(rightHand, keepVisibility: false)
        )
    }
}
