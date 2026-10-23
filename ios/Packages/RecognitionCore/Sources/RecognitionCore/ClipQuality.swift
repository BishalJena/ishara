/// How well the tracker saw a clip. The matcher refuses clips where the body or
/// hands were missing too often, however confident the embedding looks.
public struct ClipQuality: Sendable, Equatable {
    /// What the tracker found in one frame of a clip.
    public struct Frame: Sendable, Equatable {
        /// A pose was detected with both shoulders.
        public var body: Bool
        /// Number of hands with landmarks (0, 1 or 2).
        public var handCount: Int

        public init(body: Bool, handCount: Int) {
            self.body = body
            self.handCount = handCount
        }
    }

    /// Fraction of frames with the body (both shoulders) detected.
    public var poseFraction: Double
    /// Fraction of frames with at least one hand detected.
    public var handFraction: Double

    public init(poseFraction: Double, handFraction: Double) {
        self.poseFraction = poseFraction
        self.handFraction = handFraction
    }

    /// An empty clip has no evidence, so both fractions are 0.
    public static func from(frames: [Frame]) -> ClipQuality {
        guard !frames.isEmpty else { return ClipQuality(poseFraction: 0, handFraction: 0) }
        let total = Double(frames.count)
        return ClipQuality(
            poseFraction: Double(frames.count { $0.body }) / total,
            handFraction: Double(frames.count { $0.handCount >= 1 }) / total
        )
    }
}
