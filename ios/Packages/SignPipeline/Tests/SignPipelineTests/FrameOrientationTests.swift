import CoreGraphics
import XCTest
@testable import SignPipeline

final class FrameOrientationTests: XCTestCase {
    func testMapsTrackRotationsToDisplayOrientation() throws {
        XCTAssertEqual(try FrameOrientation(preferredTransform: .identity), .up)
        XCTAssertEqual(try FrameOrientation(preferredTransform: CGAffineTransform(rotationAngle: .pi / 2)), .right)
        XCTAssertEqual(try FrameOrientation(preferredTransform: CGAffineTransform(rotationAngle: .pi)), .down)
        XCTAssertEqual(try FrameOrientation(preferredTransform: CGAffineTransform(rotationAngle: -.pi / 2)), .left)
    }

    func testRejectsMirroredAndOddRotations() {
        XCTAssertThrowsError(try FrameOrientation(preferredTransform: CGAffineTransform(scaleX: -1, y: 1))) {
            XCTAssertEqual($0 as? FrameSourceError, .mirroredVideo)
        }
        XCTAssertThrowsError(try FrameOrientation(preferredTransform: CGAffineTransform(rotationAngle: .pi / 4))) {
            XCTAssertEqual($0 as? FrameSourceError, .unsupportedRotation)
        }
    }
}
