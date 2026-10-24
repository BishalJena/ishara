/// A point in normalized image coordinates: 0...1 of the upright image, `y` down.
public struct NormalizedPoint: Equatable, Sendable {
    public var x: Float
    public var y: Float

    public init(x: Float, y: Float) {
        self.x = x
        self.y = y
    }
}

/// Per-frame cues for the start/stop detector, as plain values.
public struct FrameSignals: Equatable, Sendable {
    public let timestamp: Double
    /// Both shoulders tracked (visibility ≥ 0.5), the same test `signclip.py`
    /// uses for its pose fraction and that SignCLIP normalization relies on.
    public let body: Bool
    /// Hand landmark 0 of the signer's left hand, when that hand is detected.
    public let leftWrist: NormalizedPoint?
    public let rightWrist: NormalizedPoint?

    public init(frame: LandmarkFrame) {
        timestamp = frame.timestamp
        body = frame.hasTrackedShoulders
        leftWrist = frame.leftHand.map(Self.wrist)
        rightWrist = frame.rightHand.map(Self.wrist)
    }

    private static func wrist(_ hand: [Landmark]) -> NormalizedPoint {
        let wrist = hand[SignCLIPLayout.wristIndex]
        return NormalizedPoint(x: wrist.x, y: wrist.y)
    }
}
