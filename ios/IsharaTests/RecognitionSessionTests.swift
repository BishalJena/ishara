import RecognitionCore
import SignPipeline
import XCTest
@testable import Ishara

final class RecognitionSessionTests: XCTestCase {
    private func run(_ frames: [LandmarkFrame]) -> (RecognitionSession, [RecognitionSession.Output]) {
        var session = RecognitionSession()
        let outputs = frames.flatMap { session.process($0) }
        return (session, outputs)
    }

    private func segments(_ outputs: [RecognitionSession.Output]) -> [[LandmarkFrame]] {
        outputs.compactMap { if case .segment(let frames) = $0 { frames } else { nil } }
    }

    private func cameraStates(_ outputs: [RecognitionSession.Output]) -> [CameraState] {
        outputs.compactMap { if case .camera(let state) = $0 { state } else { nil } }
    }

    func testChecklistComesFromWhatTheTrackerSees() {
        XCTAssertEqual(RecognitionSession.checks(in: Landmarks.frame(t: 0)), [.face, .bothHands, .light])
        XCTAssertEqual(RecognitionSession.checks(in: Landmarks.frame(t: 0, hands: false)), [.face, .light])
        XCTAssertEqual(RecognitionSession.checks(in: Landmarks.frame(t: 0, rightHand: false)), [.face, .light],
                       "one hand isn't both hands")
        XCTAssertEqual(RecognitionSession.checks(in: Landmarks.frame(t: 0, body: false)), [.face, .bothHands])
    }

    func testCalibratesTwoSecondsAfterTheChecklistPasses() throws {
        let (session, outputs) = run(Landmarks.run(from: 0, seconds: 2.1))

        XCTAssertEqual(Array(outputs.prefix(3)), [.passed(.bothHands), .passed(.face), .passed(.light)])
        XCTAssertTrue(outputs.contains(.calibrating(seconds: 1)))
        let restY = try XCTUnwrap(outputs.lazy.compactMap { if case .calibrated(let y) = $0 { y } else { nil } }.first)
        XCTAssertEqual(restY, 0.82, accuracy: 1e-6, "median wrist height minus the 0.08 margin")
        XCTAssertEqual(try XCTUnwrap(session.restY), restY)
    }

    func testNoSignsAreCutBeforeCalibrationEnds() {
        let (session, outputs) = run(Landmarks.sign(from: 0) + Landmarks.sign(from: 1.4))

        XCTAssertNotNil(session.restY)
        XCTAssertEqual(segments(outputs).count, 0)
        XCTAssertFalse(cameraStates(outputs).contains(.signing))
    }

    func testCalibrationStartsOverWhenTheUserCantBeSeen() {
        let frames = [Landmarks.frame(t: 0)] + Landmarks.run(from: 1.0 / 30, seconds: 2.1, body: false)

        let (session, outputs) = run(frames)

        XCTAssertTrue(outputs.contains(.calibrationRestarted(.cantSee)))
        XCTAssertFalse(outputs.contains { if case .calibrated = $0 { true } else { false } })
        XCTAssertNil(session.restY)
    }

    func testAcceptedSignHandsBackItsFramesWithPreRoll() throws {
        let (_, outputs) = run(Landmarks.calibratedStream { Landmarks.sign(from: $0) })

        let clip = try XCTUnwrap(segments(outputs).first)
        XCTAssertEqual(segments(outputs).count, 1)
        XCTAssertEqual(try XCTUnwrap(clip.first).timestamp, 2.4, accuracy: 0.02, "0.2 s pre-roll")
        XCTAssertEqual(try XCTUnwrap(clip.last).timestamp, 3.4, accuracy: 0.02, "ends when the hands rest")
        XCTAssertEqual(cameraStates(outputs), [.watching, .signing, .watching])
    }

    func testRejectedAttemptGivesNothingToMatch() {
        let (_, outputs) = run(Landmarks.calibratedStream { Landmarks.lostMidSign(from: $0) })

        XCTAssertEqual(segments(outputs).count, 0)
        XCTAssertEqual(cameraStates(outputs), [.watching, .signing, .cantSee, .watching])
    }

    func testDetectorFrameCarriesBodyAndBothWrists() {
        let frame = RecognitionSession.detectorFrame(Landmarks.frame(t: 1.5, wristY: 0.7))

        XCTAssertEqual(frame.t, 1.5)
        XCTAssertTrue(frame.body)
        XCTAssertEqual(frame.wrists.map(\.y).map { ($0 * 1000).rounded() }, [700, 700])
    }
}
