import RecognitionCore

/// Builds frame streams at a fixed frame rate from posture spans, so a test can say
/// "rest for 0.40 s" instead of listing timestamps.
struct FrameScript {
    enum Posture {
        /// Body visible, both wrists low.
        case rest
        /// Body visible, one wrist raised above the rest line.
        case active
        /// Body visible, no wrists detected.
        case noWrists
        /// Shoulders not detected.
        case unseen
    }

    static let restWristY = 0.85
    static let raisedWristY = 0.50

    let fps: Double
    let startTime: Double
    private(set) var frames: [DetectorFrame] = []

    init(fps: Double = 100, startTime: Double = 0) {
        self.fps = fps
        self.startTime = startTime
    }

    /// Time of the next frame to be added.
    var nextTime: Double { time(ofFrame: frames.count) }

    /// Adds `count` frames of `posture`.
    mutating func add(_ posture: Posture, frames count: Int) {
        for _ in 0..<count {
            frames.append(Self.frame(posture, at: nextTime))
        }
    }

    /// Adds frames so the span runs from the next frame time to `seconds` later,
    /// both ends inclusive: "rest for 0.40 s" ends with a frame 0.40 s after the first.
    mutating func add(_ posture: Posture, lasting seconds: Double) {
        add(posture, frames: Int((seconds * fps).rounded()) + 1)
    }

    static func frame(_ posture: Posture, at t: Double) -> DetectorFrame {
        let low = NormalizedPoint(x: 0.4, y: restWristY)
        switch posture {
        case .rest:
            return DetectorFrame(t: t, body: true, wrists: [low, NormalizedPoint(x: 0.6, y: restWristY)])
        case .active:
            return DetectorFrame(t: t, body: true, wrists: [low, NormalizedPoint(x: 0.6, y: raisedWristY)])
        case .noWrists:
            return DetectorFrame(t: t, body: true, wrists: [])
        case .unseen:
            return DetectorFrame(t: t, body: false, wrists: [])
        }
    }

    private func time(ofFrame index: Int) -> Double {
        startTime + Double(index) / fps
    }
}

/// Everything a detector emitted for a stream, with the frame each event came from.
struct DetectorRun {
    struct Emission: Equatable {
        let frameTime: Double
        let event: DetectorEvent
    }

    private(set) var detector: SignDetector
    private(set) var emissions: [Emission] = []

    init(restY: Double = 0.70, params: DetectorParams = DetectorParams()) {
        detector = SignDetector(restY: restY, params: params)
    }

    init(_ frames: [DetectorFrame], restY: Double = 0.70, params: DetectorParams = DetectorParams()) {
        self.init(restY: restY, params: params)
        feed(frames)
    }

    mutating func feed(_ frames: [DetectorFrame]) {
        for frame in frames {
            emissions += detector.update(frame).map { Emission(frameTime: frame.t, event: $0) }
        }
    }

    var segments: [Segment] {
        emissions.compactMap { if case .segment(let segment) = $0.event { segment } else { nil } }
    }

    var statuses: [DetectorStatus] {
        emissions.compactMap { if case .status(let status) = $0.event { status } else { nil } }
    }

    func events(at frameTime: Double) -> [DetectorEvent] {
        emissions.filter { abs($0.frameTime - frameTime) < 1e-6 }.map(\.event)
    }
}
