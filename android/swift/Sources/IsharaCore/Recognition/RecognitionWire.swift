import Foundation
import RecognitionCore
import Synchronization

// The JSON shapes recognition's JNI functions take and return, and the handle tables that keep
// detectors and matchers alive between calls. Kotlin mirrors these in
// `ai.ishara.demo.recognition.core`.

/// A RecognitionCore value Kotlin holds by a `Long` handle. Calls may come from any thread;
/// one value is never used by two threads at once.
final class HandleTable<Value: Sendable>: Sendable {
    private let entries = Mutex<(next: Int64, values: [Int64: Value])>((1, [:]))

    func add(_ value: Value) -> Int64 {
        entries.withLock { state in
            let handle = state.next
            state.next += 1
            state.values[handle] = value
            return handle
        }
    }

    /// Runs `body` on the value; nil for an unknown handle.
    func with<Result>(_ handle: Int64, _ body: (inout Value) throws -> Result) rethrows -> Result? {
        try entries.withLock { state in
            guard var value = state.values[handle] else { return nil }
            defer { state.values[handle] = value }
            return try body(&value)
        }
    }

    func remove(_ handle: Int64) {
        _ = entries.withLock { $0.values.removeValue(forKey: handle) }
    }
}

let detectors = HandleTable<SignDetector>()
let matchers = HandleTable<LogitsMatcher>()

struct UnknownHandle: Error, CustomStringConvertible {
    let kind: String
    let handle: Int64
    var description: String { "no \(kind) with handle \(handle)" }
}

struct UnknownParameter: Error, CustomStringConvertible {
    let name: String
    var description: String { "unknown detector parameter \(name)" }
}

/// Detector tuning keyed by the shared spec's snake_case names (the detector fixtures use them).
enum DetectorParamsWire {
    static func decode(_ json: String) throws -> DetectorParams {
        let overrides = try JSONDecoder().decode([String: Double].self, from: Data(json.utf8))
        var params = DetectorParams()
        for (name, value) in overrides {
            guard let keyPath = keyPaths[name] else { throw UnknownParameter(name: name) }
            params[keyPath: keyPath] = value
        }
        return params
    }

    static func encode(_ params: DetectorParams) -> String {
        encodeJSON(keyPaths.mapValues { params[keyPath: $0] })
    }

    private nonisolated(unsafe) static let keyPaths: [String: WritableKeyPath<DetectorParams, Double>] = [
        "calibration_s": \.calibrationS,
        "rest_margin": \.restMargin,
        "default_rest_y": \.defaultRestY,
        "rest_y_min": \.restYMin,
        "rest_y_max": \.restYMax,
        "min_body_fraction": \.minBodyFraction,
        "start_hold_s": \.startHoldS,
        "end_rest_s": \.endRestS,
        "pre_roll_s": \.preRollS,
        "min_sign_s": \.minSignS,
        "max_sign_s": \.maxSignS,
        "lost_body_s": \.lostBodyS,
    ]
}

/// `{"t": 1.5, "body": true, "wrists": [[x, y], …]}`, as in the detector fixtures.
struct DetectorFrameWire: Decodable {
    let t: Double
    let body: Bool
    let wrists: [[Double]]

    func frame() throws -> DetectorFrame {
        DetectorFrame(t: t, body: body, wrists: try wrists.map { point in
            guard point.count == 2 else { throw DecodingError.dataCorrupted(.init(codingPath: [], debugDescription: "a wrist is [x, y]")) }
            return NormalizedPoint(x: point[0], y: point[1])
        })
    }
}

/// `{"restY": Double}` or `{"error": "too_short" | "cant_see"}`.
struct CalibrationOutput: Encodable {
    var restY: Double?
    var error: String?
}

/// One detector event: `{"status": "watching"}` or `{"segment": {"start", "end", "reason"}}`.
struct DetectorEventWire: Encodable {
    struct SegmentWire: Encodable {
        let start: Double
        let end: Double
        /// Always present, null for an accepted segment.
        let reason: String?

        func encode(to encoder: any Encoder) throws {
            var container = encoder.container(keyedBy: CodingKeys.self)
            try container.encode(start, forKey: .start)
            try container.encode(end, forKey: .end)
            try container.encode(reason, forKey: .reason)
        }

        enum CodingKeys: String, CodingKey { case start, end, reason }
    }

    var status: String?
    var segment: SegmentWire?

    init(_ event: DetectorEvent) {
        switch event {
        case .status(let status):
            self.status = status.rawValue
        case .segment(let segment):
            self.segment = SegmentWire(start: segment.start, end: segment.end, reason: segment.reason?.rawValue)
        }
    }
}

/// `FramingGuard.Frame` as JSON: `{"timestamp", "left": {"tracked", "wristX"?, "wristY"?}, "right": …}`.
struct FramingFrameWire: Decodable {
    struct Hand: Decodable {
        let tracked: Bool
        let wristX: Float?
        let wristY: Float?
    }

    let timestamp: Double
    let left: Hand
    let right: Hand

    var frame: FramingGuard.Frame {
        func hand(_ wire: Hand) -> FramingGuard.Hand {
            FramingGuard.Hand(tracked: wire.tracked, wristX: wire.wristX, wristY: wire.wristY)
        }
        return FramingGuard.Frame(timestamp: timestamp, left: hand(left), right: hand(right))
    }
}

struct QualityFrameWire: Decodable {
    let body: Bool
    let handCount: Int
}

struct QualityOutput: Encodable {
    let poseFraction: Double
    let handFraction: Double
}

struct MatcherInfo: Encodable {
    let provisional: Bool
    let classCount: Int
    let vocabulary: [String]
}
