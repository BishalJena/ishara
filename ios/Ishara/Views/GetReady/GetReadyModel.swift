import Foundation
import Observation

/// Framing checklist plus the 2 s "hands at rest" calibration that teaches the
/// start/stop detector what rest looks like (PLAN §4).
///
/// The simulator has no camera, so `runSimulatedChecks()` ticks the checklist on
/// timers. The camera-based check replaces it when the sign pipeline lands (P2).
@MainActor
@Observable
final class GetReadyModel {
    enum Check: String, CaseIterable, Identifiable {
        case face, bothHands, light

        var id: String { rawValue }

        var title: String {
            switch self {
            case .face: "Face visible"
            case .bothHands: "Both hands visible"
            case .light: "Good light"
            }
        }
    }

    static let calibrationSeconds: Double = 2

    private(set) var passedChecks: Set<Check> = []
    private(set) var secondsAtRest: Double = 0

    /// 0...1 progress of the hands-at-rest calibration.
    var calibrationProgress: Double { min(1, secondsAtRest / Self.calibrationSeconds) }

    var allChecksPassed: Bool { passedChecks.count == Check.allCases.count }
    /// Small tolerance so summed timer steps can't fall a hair short of 2 s.
    var isCalibrated: Bool { secondsAtRest + 0.001 >= Self.calibrationSeconds }
    var isReady: Bool { allChecksPassed && isCalibrated }

    func pass(_ check: Check) {
        passedChecks.insert(check)
    }

    func advanceCalibration(by seconds: Double) {
        guard allChecksPassed else { return }
        secondsAtRest = min(Self.calibrationSeconds, secondsAtRest + seconds)
    }

    func runSimulatedChecks(timeScale: Double = 1) async {
        for check in Check.allCases {
            guard await pause(0.6 * timeScale) else { return }
            pass(check)
        }
        let step = 0.1
        while !isCalibrated {
            guard await pause(step * timeScale) else { return }
            advanceCalibration(by: step)
        }
    }

    /// Returns false when the task was cancelled (the screen went away).
    private func pause(_ seconds: Double) async -> Bool {
        do {
            try await Task.sleep(for: .seconds(seconds))
            return true
        } catch {
            return false
        }
    }
}
