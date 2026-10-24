import XCTest
@testable import SignPipeline

final class LandmarkFrameTests: XCTestCase {
    private let size = ImageSize(width: 640, height: 480)

    func testAcceptsEveryPartMissing() throws {
        let frame = try LandmarkFrame(timestamp: 0, imageSize: size)
        XCTAssertNil(frame.pose)
        XCTAssertNil(frame.face)
        XCTAssertNil(frame.leftHand)
        XCTAssertNil(frame.rightHand)
    }

    func testRejectsWrongPoseCount() {
        let pose = Array(Synthetic.pose().dropLast())
        XCTAssertThrowsError(try LandmarkFrame(timestamp: 0, imageSize: size, pose: pose)) {
            XCTAssertEqual($0 as? LandmarkFrameError, .unexpectedLandmarkCount(.pose, 32))
        }
    }

    func testRejectsTruncatedFaceButAcceptsIrisRefinedMesh() {
        let face = Synthetic.face()
        XCTAssertThrowsError(try LandmarkFrame(timestamp: 0, imageSize: size, face: Array(face.dropLast()))) {
            XCTAssertEqual($0 as? LandmarkFrameError, .unexpectedLandmarkCount(.face, 467))
        }
        let iris = Array(repeating: Landmark(x: 0.5, y: 0.5, z: 0), count: 10)
        XCTAssertNoThrow(try LandmarkFrame(timestamp: 0, imageSize: size, face: face + iris))
    }

    func testRejectsWrongHandCountOnEitherSide() {
        let hand = Synthetic.hand(x: 0.5) + [Landmark(x: 0, y: 0, z: 0)]
        XCTAssertThrowsError(try LandmarkFrame(timestamp: 0, imageSize: size, leftHand: hand)) {
            XCTAssertEqual($0 as? LandmarkFrameError, .unexpectedLandmarkCount(.leftHand, 22))
        }
        XCTAssertThrowsError(try LandmarkFrame(timestamp: 0, imageSize: size, rightHand: hand)) {
            XCTAssertEqual($0 as? LandmarkFrameError, .unexpectedLandmarkCount(.rightHand, 22))
        }
    }

    func testRejectsNonFiniteCoordinates() {
        var hand = Synthetic.hand(x: 0.5)
        hand[3].z = .nan
        XCTAssertThrowsError(try LandmarkFrame(timestamp: 0, imageSize: size, rightHand: hand)) {
            XCTAssertEqual($0 as? LandmarkFrameError, .nonFiniteLandmark(.rightHand))
        }
    }

    func testRejectsEmptyImage() {
        let empty = ImageSize(width: 0, height: 480)
        XCTAssertThrowsError(try LandmarkFrame(timestamp: 0, imageSize: empty)) {
            XCTAssertEqual($0 as? LandmarkFrameError, .invalidImageSize(empty))
        }
    }
}
