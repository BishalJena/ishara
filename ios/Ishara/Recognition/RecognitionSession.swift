import Foundation
import RecognitionCore
import SignPipeline

/// The frame-by-frame logic between landmarks and the matcher, with no threads, camera
/// or Core ML, so it can be tested with scripted landmark frames.
///
/// 1. Framing: ticks the Get ready checklist from what the tracker sees.
/// 2. Calibrating: once every check has passed, collects `calibrationS` of frames and
///    asks `SignDetector.calibrate` for the rest line (retrying if it can't see the user).
/// 3. Detecting: feeds `SignDetector`, maps its status to the camera pill and hands back
///    the landmark frames of every **accepted** segment. Rejected segments give nothing.
struct RecognitionSession {
    enum Output: Equatable {
        case passed(GetReadyModel.Check)
        /// Seconds of calibration recording collected so far.
        case calibrating(seconds: Double)
        /// The recording couldn't be used; calibration starts over.
        case calibrationRestarted(CalibrationError)
        case calibrated(restY: Double)
        case camera(CameraState)
        /// The frames of one accepted sign, from the detector's start to its end.
        case segment([LandmarkFrame])
    }

    private enum Phase {
        case framing
        case calibrating(start: Double)
        case detecting(SignDetector)
    }

    let params: DetectorParams
    private var phase: Phase = .framing
    private var passed: Set<GetReadyModel.Check> = []
    private var calibrationFrames: [DetectorFrame] = []
    /// Recent frames, long enough to cover a whole sign plus pre-roll and the rest that ends it.
    private var recent: [LandmarkFrame] = []

    init(params: DetectorParams = DetectorParams()) {
        self.params = params
    }

    var restY: Double? {
        if case .detecting(let detector) = phase { detector.restY } else { nil }
    }

    mutating func process(_ frame: LandmarkFrame) -> [Output] {
        let detectorFrame = Self.detectorFrame(frame)
        switch phase {
        case .framing:
            let newlyPassed = Self.checks(in: frame).subtracting(passed).sorted { $0.rawValue < $1.rawValue }
            passed.formUnion(newlyPassed)
            if passed.count == GetReadyModel.Check.allCases.count {
                phase = .calibrating(start: frame.timestamp)
                calibrationFrames = [detectorFrame]
            }
            return newlyPassed.map(Output.passed)

        case .calibrating(let start):
            calibrationFrames.append(detectorFrame)
            let seconds = frame.timestamp - start
            guard seconds >= params.calibrationS else { return [.calibrating(seconds: seconds)] }
            do {
                let restY = try SignDetector.calibrate(frames: calibrationFrames, params: params)
                phase = .detecting(SignDetector(restY: restY, params: params))
                calibrationFrames = []
                return [.calibrating(seconds: seconds), .calibrated(restY: restY)]
            } catch {
                phase = .calibrating(start: frame.timestamp)
                calibrationFrames = [detectorFrame]
                return [.calibrationRestarted(error)]
            }

        case .detecting(var detector):
            remember(frame)
            let events = detector.update(detectorFrame)
            phase = .detecting(detector)
            return events.compactMap(output(for:))
        }
    }

    private mutating func remember(_ frame: LandmarkFrame) {
        recent.append(frame)
        let horizon = params.maxSignS + params.preRollS + params.endRestS + 1
        recent.removeAll { $0.timestamp < frame.timestamp - horizon }
    }

    private func output(for event: DetectorEvent) -> Output? {
        switch event {
        case .status(let status):
            return .camera(CameraState(status))
        case .segment(let segment):
            guard segment.accepted else { return nil }
            return .segment(recent.filter { segment.start <= $0.timestamp && $0.timestamp <= segment.end })
        }
    }

    /// No light meter: "Good light" passes once the tracker finds both shoulders, i.e. the
    /// picture is good enough to track.
    static func checks(in frame: LandmarkFrame) -> Set<GetReadyModel.Check> {
        var checks: Set<GetReadyModel.Check> = []
        if frame.face != nil { checks.insert(.face) }
        if frame.leftHand != nil, frame.rightHand != nil { checks.insert(.bothHands) }
        if frame.hasTrackedShoulders { checks.insert(.light) }
        return checks
    }

    static func detectorFrame(_ frame: LandmarkFrame) -> DetectorFrame {
        let signals = FrameSignals(frame: frame)
        let wrists = [signals.leftWrist, signals.rightWrist].compactMap { point in
            point.map { RecognitionCore.NormalizedPoint(x: Double($0.x), y: Double($0.y)) }
        }
        return DetectorFrame(t: signals.timestamp, body: signals.body, wrists: wrists)
    }
}

extension CameraState {
    init(_ status: DetectorStatus) {
        switch status {
        case .watching: self = .watching
        case .signing: self = .signing
        case .cantSee: self = .cantSee
        }
    }
}
