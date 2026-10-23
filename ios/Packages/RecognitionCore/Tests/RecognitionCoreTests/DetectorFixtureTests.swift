import Foundation
import RecognitionCore
import XCTest

/// Runs every shared detector fixture (`Fixtures/detector/*.json`). The same files
/// drive the Python detector, so both implementations must cut identical clips.
final class DetectorFixtureTests: XCTestCase {
    func testEveryDetectorFixture() throws {
        let directory = try XCTUnwrap(
            Bundle.module.url(forResource: "detector", withExtension: nil, subdirectory: "Fixtures"),
            "fixture directory missing from the test bundle"
        )
        let files = try FileManager.default
            .contentsOfDirectory(at: directory, includingPropertiesForKeys: nil)
            .filter { $0.pathExtension == "json" }
            .sorted { $0.lastPathComponent < $1.lastPathComponent }
        XCTAssertFalse(files.isEmpty, "no detector fixtures found")

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        for file in files {
            let fixture = try decoder.decode(DetectorFixture.self, from: Data(contentsOf: file))
            try check(fixture, file: file.lastPathComponent)
        }
    }

    private func check(_ fixture: DetectorFixture, file: String) throws {
        let label = "\(file) (\(fixture.name))"
        let params = try fixture.detectorParams()

        let restY: Double
        do throws(CalibrationError) {
            restY = try SignDetector.calibrate(frames: fixture.calibration.map(\.frame), params: params)
        } catch {
            XCTAssertEqual(error.rawValue, fixture.expectedCalibrationError, "\(label): calibration error")
            XCTAssertTrue(fixture.frames.isEmpty, "\(label): a fixture that fails calibration has no frames")
            return
        }
        XCTAssertNil(fixture.expectedCalibrationError, "\(label): calibration should have failed")
        if let expected = fixture.expectedRestY {
            XCTAssertEqual(restY, expected, accuracy: 1e-9, "\(label): rest_y")
        }

        var detector = SignDetector(restY: restY, params: params)
        var segments: [Segment] = []
        var statuses: [String] = []
        for frame in fixture.frames {
            for event in detector.update(frame.frame) {
                switch event {
                case .segment(let segment): segments.append(segment)
                case .status(let status): statuses.append(status.rawValue)
                }
            }
        }

        XCTAssertEqual(statuses, fixture.expectedStatuses, "\(label): statuses")
        XCTAssertEqual(segments.count, fixture.expectedSegments.count, "\(label): segment count")
        for (actual, expected) in zip(segments, fixture.expectedSegments) {
            XCTAssertEqual(actual.start, expected.start, accuracy: 1e-6, "\(label): segment start")
            XCTAssertEqual(actual.end, expected.end, accuracy: 1e-6, "\(label): segment end")
            XCTAssertEqual(actual.accepted, expected.accepted, "\(label): segment accepted")
            XCTAssertEqual(actual.reason?.rawValue, expected.reason, "\(label): segment reason")
        }
    }
}

private struct DetectorFixture: Decodable {
    struct Frame: Decodable {
        let t: Double
        let body: Bool
        let wrists: [[Double]]

        var frame: DetectorFrame {
            DetectorFrame(t: t, body: body, wrists: wrists.map { NormalizedPoint(x: $0[0], y: $0[1]) })
        }
    }

    struct ExpectedSegment: Decodable {
        let start: Double
        let end: Double
        let accepted: Bool
        let reason: String?
    }

    struct UnknownParameter: Error, CustomStringConvertible {
        let name: String
        var description: String { "unknown detector parameter \(name)" }
    }

    let name: String
    /// Overrides keyed by the snake_case spec names (left as-is by the decoder for dictionary keys).
    let params: [String: Double]
    let calibration: [Frame]
    let frames: [Frame]
    let expectedRestY: Double?
    let expectedCalibrationError: String?
    let expectedSegments: [ExpectedSegment]
    let expectedStatuses: [String]

    func detectorParams() throws -> DetectorParams {
        var result = DetectorParams()
        for (name, value) in params {
            switch name {
            case "calibration_s": result.calibrationS = value
            case "rest_margin": result.restMargin = value
            case "default_rest_y": result.defaultRestY = value
            case "rest_y_min": result.restYMin = value
            case "rest_y_max": result.restYMax = value
            case "min_body_fraction": result.minBodyFraction = value
            case "start_hold_s": result.startHoldS = value
            case "end_rest_s": result.endRestS = value
            case "pre_roll_s": result.preRollS = value
            case "min_sign_s": result.minSignS = value
            case "max_sign_s": result.maxSignS = value
            case "lost_body_s": result.lostBodyS = value
            default: throw UnknownParameter(name: name)
            }
        }
        return result
    }
}
