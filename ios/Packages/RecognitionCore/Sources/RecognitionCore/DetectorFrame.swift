/// A point in normalized image coordinates: both axes in [0, 1], y grows downward.
public struct NormalizedPoint: Sendable, Equatable {
    public var x: Double
    public var y: Double

    public init(x: Double, y: Double) {
        self.x = x
        self.y = y
    }
}

/// What the pose tracker saw in one camera frame.
public struct DetectorFrame: Sendable, Equatable {
    /// Monotonic timestamp in seconds.
    public var t: Double
    /// A pose was detected with both shoulders.
    public var body: Bool
    /// Detected wrists (zero, one or two).
    public var wrists: [NormalizedPoint]

    public init(t: Double, body: Bool, wrists: [NormalizedPoint] = []) {
        self.t = t
        self.body = body
        self.wrists = wrists
    }
}
