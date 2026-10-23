import XCTest
@testable import SignPipeline

final class HolisticLandmarksTests: XCTestCase {
    private let size = ImageSize(width: 720, height: 1280)

    func testEmptyListsMeanUndetectedParts() throws {
        let frame = try LandmarkFrame.holistic(
            timestamp: 2, imageSize: size, pose: [], face: [], leftHand: [], rightHand: []
        )
        XCTAssertNil(frame.pose)
        XCTAssertNil(frame.face)
        XCTAssertNil(frame.leftHand)
        XCTAssertNil(frame.rightHand)
        XCTAssertEqual(frame.timestamp, 2)
        XCTAssertEqual(frame.imageSize, size)
    }

    func testKeepsPoseVisibilityButDropsFaceAndHandScores() throws {
        let scored = { (points: [Landmark]) in points.map { Landmark(x: $0.x, y: $0.y, z: $0.z, visibility: 0) } }
        let pose = Synthetic.pose(visibility: 0.8)

        let frame = try LandmarkFrame.holistic(
            timestamp: 0, imageSize: size, pose: pose, face: scored(Synthetic.face()),
            leftHand: scored(Synthetic.hand(x: 0.6)), rightHand: scored(Synthetic.hand(x: 0.3))
        )

        XCTAssertEqual(frame.pose, pose)
        XCTAssertEqual(frame.face, Synthetic.face())
        XCTAssertEqual(frame.leftHand, Synthetic.hand(x: 0.6))
        XCTAssertEqual(frame.rightHand, Synthetic.hand(x: 0.3))
    }

    func testKeepsHandsOnTheSideTheGraphAssigned() throws {
        let frame = try LandmarkFrame.holistic(
            timestamp: 0, imageSize: size, pose: [], face: [],
            leftHand: Synthetic.hand(x: 0.6), rightHand: []
        )
        XCTAssertEqual(frame.leftHand, Synthetic.hand(x: 0.6))
        XCTAssertNil(frame.rightHand)
    }

    func testStillValidatesCounts() {
        XCTAssertThrowsError(try LandmarkFrame.holistic(
            timestamp: 0, imageSize: size, pose: [Landmark(x: 0, y: 0, z: 0)], face: [], leftHand: [], rightHand: []
        )) {
            XCTAssertEqual($0 as? LandmarkFrameError, .unexpectedLandmarkCount(.pose, 1))
        }
    }
}
