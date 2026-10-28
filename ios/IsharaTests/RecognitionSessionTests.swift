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

    private func clips(_ outputs: [RecognitionSession.Output]) -> [RecognitionSession.SignClip] {
        outputs.compactMap { if case .segment(let clip) = $0 { clip } else { nil } }
    }

    private func segments(_ outputs: [RecognitionSession.Output]) -> [[LandmarkFrame]] {
        clips(outputs).map(\.frames)
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

    func testAcceptedSignCarriesTheCalibratedRestLine() throws {
        let (session, outputs) = run(Landmarks.calibratedStream { Landmarks.sign(from: $0) })

        let clip = try XCTUnwrap(clips(outputs).first)
        XCTAssertEqual(clip.restY, try XCTUnwrap(session.restY))
        XCTAssertEqual(clip.restY, Landmarks.calibratedRestY, accuracy: 1e-6)
    }

    func testAcceptedSignAlsoHandsBackTheRestThatEndedIt() throws {
        let (_, outputs) = run(Landmarks.calibratedStream { Landmarks.sign(from: $0) })

        let clip = try XCTUnwrap(clips(outputs).first)
        let end = try XCTUnwrap(clip.frames.last).timestamp
        XCTAssertTrue(clip.restAfter.allSatisfy { $0.timestamp > end }, "no frame twice")
        XCTAssertEqual(try XCTUnwrap(clip.restAfter.first).timestamp, end + 1.0 / 30, accuracy: 1e-6,
                       "starts right after the cut")
        XCTAssertEqual(try XCTUnwrap(clip.restAfter.last).timestamp - end, 0.4, accuracy: 0.02,
                       "up to the frame that ended the sign, 0.4 s of rest later")
        XCTAssertTrue(clip.restAfter.allSatisfy { $0.leftHand?.first?.y == Landmarks.restY })
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
