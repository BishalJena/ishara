import XCTest
@testable import SignPipeline

final class FrameSignalsTests: XCTestCase {
    func testReportsBodyAndBothWristsInNormalizedCoordinates() {
        var left = Synthetic.hand(x: 0.6)
        left[0] = Landmark(x: 0.61, y: 0.72, z: -0.3)
        var right = Synthetic.hand(x: 0.3)
        right[0] = Landmark(x: 0.31, y: 0.83, z: -0.1)

        let signals = FrameSignals(frame: Synthetic.frame(timestamp: 1.5, leftHand: left, rightHand: right))

        XCTAssertEqual(signals.timestamp, 1.5)
        XCTAssertTrue(signals.body)
        XCTAssertEqual(signals.leftWrist, NormalizedPoint(x: 0.61, y: 0.72))
        XCTAssertEqual(signals.rightWrist, NormalizedPoint(x: 0.31, y: 0.83))
    }

    func testMissingHandsGiveNoWrists() {
        let signals = FrameSignals(frame: Synthetic.frame(leftHand: nil, rightHand: nil))
        XCTAssertNil(signals.leftWrist)
        XCTAssertNil(signals.rightWrist)
        XCTAssertTrue(signals.body)
    }

    func testNoBodyWithoutPose() {
        XCTAssertFalse(FrameSignals(frame: Synthetic.frame(pose: nil)).body)
    }

    func testNoBodyWhenEitherShoulderIsBelowThreshold() {
        for shoulder in [SignCLIPLayout.Pose.leftShoulder, SignCLIPLayout.Pose.rightShoulder] {
            var pose = Synthetic.pose()
            pose[shoulder].visibility = 0.49
            XCTAssertFalse(FrameSignals(frame: Synthetic.frame(pose: pose)).body, "shoulder \(shoulder)")
            pose[shoulder].visibility = 0.5
            XCTAssertTrue(FrameSignals(frame: Synthetic.frame(pose: pose)).body, "shoulder \(shoulder)")
        }
    }

    func testOtherLowVisibilityLandmarksDoNotHideTheBody() {
        var pose = Synthetic.pose()
        pose[0].visibility = 0
        pose[SignCLIPLayout.Pose.legs.lowerBound].visibility = 0
        XCTAssertTrue(FrameSignals(frame: Synthetic.frame(pose: pose)).body)
    }
}
