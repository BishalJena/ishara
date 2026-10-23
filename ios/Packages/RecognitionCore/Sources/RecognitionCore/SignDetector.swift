/// The camera pill colour shown to the user.
public enum DetectorStatus: String, Sendable, Equatable {
    /// Green: hands at rest, waiting for a sign.
    case watching
    /// Yellow: a sign is in progress, or the detector waits for the hands to settle.
    case signing
    /// Red: the user is out of frame.
    case cantSee = "cant_see"
}

/// A stretch of video the detector cut out as one sign attempt.
public struct Segment: Sendable, Equatable {
    public enum RejectionReason: String, Sendable, Equatable {
        case tooShort = "too_short"
        case tooLong = "too_long"
        case lostTracking = "lost_tracking"
    }

    public var start: Double
    public var end: Double
    /// Why the clip must not be sent to the matcher; `nil` for an accepted clip.
    public var reason: RejectionReason?

    public var accepted: Bool { reason == nil }

    public init(start: Double, end: Double, reason: RejectionReason? = nil) {
        self.start = start
        self.end = end
        self.reason = reason
    }
}

public enum DetectorEvent: Sendable, Equatable {
    case status(DetectorStatus)
    case segment(Segment)
}

/// Cuts a stream of pose frames into one-sign clips: hands leave rest to start,
/// hands back at rest for `endRestS` to end. Pure value type; feed it frames in
/// time order.
public struct SignDetector: Sendable {
    public enum State: Sendable, Equatable {
        case watching
        case signing(start: Double)
        /// After an over-long attempt: wait for the hands to rest before watching again.
        case cooldown
        case cantSee
    }

    public let restY: Double
    public let params: DetectorParams
    public private(set) var state: State = .watching

    private var firstFrameTime: Double?
    private var reportedStatus: DetectorStatus?
    private var activeRun = Run()
    private var restRun = Run()
    private var lostRun = Run()

    public init(restY: Double, params: DetectorParams = DetectorParams()) {
        self.restY = restY
        self.params = params
    }

    public var status: DetectorStatus {
        switch state {
        case .watching: .watching
        case .signing, .cooldown: .signing
        case .cantSee: .cantSee
        }
    }

    /// Processes one frame. Returns at most one segment followed by at most one
    /// status change; the first frame always reports the initial status.
    public mutating func update(_ frame: DetectorFrame) -> [DetectorEvent] {
        let t = frame.t
        if firstFrameTime == nil { firstFrameTime = t }

        let active = frame.body && frame.wrists.contains { $0.y < restY }
        let rest = frame.body && !active
        activeRun.track(active, at: t)
        restRun.track(rest, at: t)
        lostRun.track(!frame.body, at: t)

        var events: [DetectorEvent] = []
        if let segment = advance(at: t, body: frame.body, rest: rest) {
            events.append(.segment(segment))
        }
        if status != reportedStatus {
            reportedStatus = status
            events.append(.status(status))
        }
        return events
    }

    private mutating func advance(at t: Double, body: Bool, rest: Bool) -> Segment? {
        if state != .cantSee, lostRun.hasLasted(params.lostBodyS, at: t) {
            defer { state = .cantSee }
            if case .signing(let start) = state {
                return Segment(start: start, end: t, reason: .lostTracking)
            }
            return nil
        }

        switch state {
        case .cantSee:
            if body { state = rest ? .watching : .cooldown }

        case .watching:
            if activeRun.hasLasted(params.startHoldS, at: t), let firstActive = activeRun.start {
                let start = max(firstFrameTime ?? t, firstActive - params.preRollS)
                state = .signing(start: start)
            }

        case .signing(let start):
            if restRun.hasLasted(params.endRestS, at: t), let end = restRun.start {
                state = .watching
                let tooShort = end - start < params.minSignS
                return Segment(start: start, end: end, reason: tooShort ? .tooShort : nil)
            }
            if t - start > params.maxSignS {
                state = .cooldown
                return Segment(start: start, end: t, reason: .tooLong)
            }

        case .cooldown:
            if restRun.hasLasted(params.endRestS, at: t) { state = .watching }
        }
        return nil
    }
}

/// A run of consecutive frames for which a condition held.
private struct Run: Sendable {
    private(set) var start: Double?

    mutating func track(_ holds: Bool, at t: Double) {
        if !holds {
            start = nil
        } else if start == nil {
            start = t
        }
    }

    func hasLasted(_ duration: Double, at t: Double) -> Bool {
        guard let start else { return false }
        return t - start >= duration - DetectorParams.timeTolerance
    }
}
