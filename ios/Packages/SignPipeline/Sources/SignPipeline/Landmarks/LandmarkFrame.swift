/// One landmark in normalized image coordinates, as MediaPipe reports it:
/// `x` and `y` in 0...1 of the upright image with `y` pointing down, and `z`
/// as depth on roughly the same scale as `x`.
public struct Landmark: Equatable, Sendable {
    public var x: Float
    public var y: Float
    public var z: Float
    /// Pose landmarks carry a visibility score; face and hand landmarks don't.
    public var visibility: Float?

    public init(x: Float, y: Float, z: Float, visibility: Float? = nil) {
        self.x = x
        self.y = y
        self.z = z
        self.visibility = visibility
    }
}

/// Pixel size of the upright image the landmarks were detected in.
public struct ImageSize: Equatable, Sendable {
    public var width: Int
    public var height: Int

    public init(width: Int, height: Int) {
        self.width = width
        self.height = height
    }
}

/// Holistic landmarks for a single video frame. A `nil` part was not detected.
public struct LandmarkFrame: Equatable, Sendable {
    public static let poseCount = 33
    /// Legacy Holistic face mesh size; the Holistic Landmarker adds 10 iris points.
    public static let minimumFaceCount = 468
    public static let handCount = 21

    /// Presentation time of the source frame, in seconds.
    public var timestamp: Double
    public var imageSize: ImageSize
    public var pose: [Landmark]?
    public var face: [Landmark]?
    /// The signer's left hand, as assigned by the Holistic graph.
    public var leftHand: [Landmark]?
    public var rightHand: [Landmark]?

    public init(
        timestamp: Double,
        imageSize: ImageSize,
        pose: [Landmark]? = nil,
        face: [Landmark]? = nil,
        leftHand: [Landmark]? = nil,
        rightHand: [Landmark]? = nil
    ) throws {
        guard imageSize.width > 0, imageSize.height > 0 else {
            throw LandmarkFrameError.invalidImageSize(imageSize)
        }
        try Self.check(pose, part: .pose) { $0 == Self.poseCount }
        try Self.check(face, part: .face) { $0 >= Self.minimumFaceCount }
        try Self.check(leftHand, part: .leftHand) { $0 == Self.handCount }
        try Self.check(rightHand, part: .rightHand) { $0 == Self.handCount }
        self.timestamp = timestamp
        self.imageSize = imageSize
        self.pose = pose
        self.face = face
        self.leftHand = leftHand
        self.rightHand = rightHand
    }

    private static func check(
        _ landmarks: [Landmark]?, part: BodyPart, count isValid: (Int) -> Bool
    ) throws {
        guard let landmarks else { return }
        guard isValid(landmarks.count) else {
            throw LandmarkFrameError.unexpectedLandmarkCount(part, landmarks.count)
        }
        guard landmarks.allSatisfy({ $0.x.isFinite && $0.y.isFinite && $0.z.isFinite }) else {
            throw LandmarkFrameError.nonFiniteLandmark(part)
        }
    }
}

extension Landmark {
    /// Confidence as pose-format reads a pose landmark. A pose result without a
    /// visibility score still means the landmark was detected.
    public var poseConfidence: Float { visibility ?? 1 }
}

extension LandmarkFrame {
    public static let minimumTrackedShoulderVisibility: Float = 0.5

    /// Both shoulders have pose confidence ≥ 0.5.
    public var hasTrackedShoulders: Bool {
        guard let pose else { return false }
        return [SignCLIPLayout.Pose.leftShoulder, SignCLIPLayout.Pose.rightShoulder].allSatisfy {
            pose[$0].poseConfidence >= Self.minimumTrackedShoulderVisibility
        }
    }
}

public enum BodyPart: String, Sendable {
    case pose, face, leftHand, rightHand
}

public enum LandmarkFrameError: Error, Equatable {
    case invalidImageSize(ImageSize)
    case unexpectedLandmarkCount(BodyPart, Int)
    case nonFiniteLandmark(BodyPart)
}
