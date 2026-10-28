/// Explains a `?` when a hand left the picture during the sign. A portrait phone frame is
/// narrow: in the 25 Oct probe, cropping the same takes to 9:16 dropped `no` from 0.64 to 0.42
/// and lost `morning`, because hands that drift sideways become missing landmarks
/// (docs/experiments/asl-model-probe.md). The guard never makes a chip; when it fires the sign
/// was read from a partial view, so the result is a `?` that tells the user why, and they keep
/// their hands inside the frame next time.
///
/// A hand counts as out of frame in a frame when its hand landmarks are missing and the pose's
/// estimate of that wrist (MediaPipe keeps estimating joints outside the image) lies beyond
/// the left, right or top edge while still above the rest line. A wrist at or below the rest
/// line is resting: in a narrow portrait frame the resting arms hang past the side edges
/// (pose wrists at x ≈ -0.1 / 1.17, y ≈ 0.95 in the 9:16 Lifeprint crops, issue #58).
public enum FramingGuard {
    /// Longer than this out of frame, inside one sign, explains the `?`.
    public static let maxOutOfFrameSeconds = 0.3
    /// Normalized distance from an edge that already counts as outside.
    public static let edgeMargin: Float = 0.02

    public struct Hand: Sendable, Equatable {
        public var tracked: Bool
        /// The pose's wrist for this side, in normalized image coordinates; nil without a pose.
        public var wristX: Float?
        public var wristY: Float?

        public init(tracked: Bool, wristX: Float? = nil, wristY: Float? = nil) {
            self.tracked = tracked
            self.wristX = wristX
            self.wristY = wristY
        }

        func isOutOfFrame(restY: Double) -> Bool {
            guard !tracked, let wristX, let wristY, Double(wristY) < restY else { return false }
            return wristX < edgeMargin || wristX > 1 - edgeMargin || wristY < edgeMargin
        }
    }

    public struct Frame: Sendable, Equatable {
        public var timestamp: Double
        public var left: Hand
        public var right: Hand

        public init(timestamp: Double, left: Hand, right: Hand) {
            self.timestamp = timestamp
            self.left = left
            self.right = right
        }
    }

    /// True when a hand that took part in the sign was out of frame for longer than
    /// `maxOutOfFrameSeconds` in one stretch. `restY` is the detector's calibrated rest line.
    public static func handLeftFrame(_ frames: [Frame], restY: Double) -> Bool {
        guard frames.count >= 2 else { return false }
        let step = (frames[frames.count - 1].timestamp - frames[0].timestamp) / Double(frames.count - 1)
        return [\Frame.left, \Frame.right].contains { side in
            let hands = frames.map { $0[keyPath: side] }
            guard hands.contains(where: \.tracked) else { return false }
            let samples = hands.indices.map { (frames[$0].timestamp, hands[$0].isOutOfFrame(restY: restY)) }
            return longestOutOfFrameRun(samples, step: step) > maxOutOfFrameSeconds
        }
    }

    private static func longestOutOfFrameRun(_ samples: [(Double, Bool)], step: Double) -> Double {
        var longest = 0.0
        var start: Double?
        for (index, (timestamp, out)) in samples.enumerated() {
            if out, start == nil { start = timestamp }
            let runEnds = !out || index == samples.count - 1
            if let begun = start, runEnds {
                let end = out ? timestamp + step : timestamp
                longest = max(longest, end - begun)
                start = nil
            }
        }
        return longest
    }
}
