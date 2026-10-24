import CoreGraphics
import SignPipeline
import XCTest
@testable import Ishara

final class BodyOverlayTests: XCTestCase {
    func testTakesTrackedShouldersWristsAndTheRestLine() {
        let overlay = BodyOverlay(frame: Landmarks.frame(t: 0, wristY: 0.7), restY: 0.8)

        XCTAssertEqual(overlay.imageSize, CGSize(width: 720, height: 1280))
        XCTAssertEqual(overlay.shoulders.map(rounded), [CGPoint(x: 0.6, y: 0.4), CGPoint(x: 0.4, y: 0.4)].map(rounded))
        XCTAssertEqual(overlay.wrists.map(rounded), [CGPoint(x: 0.6, y: 0.7), CGPoint(x: 0.4, y: 0.7)].map(rounded))
        XCTAssertEqual(overlay.restY, 0.8)
    }

    func testLeavesOutShouldersAndHandsTheTrackerLost() {
        let overlay = BodyOverlay(frame: Landmarks.frame(t: 0, body: false, rightHand: false), restY: nil)

        XCTAssertEqual(overlay.shoulders, [], "low-visibility shoulders would draw dots in the wrong place")
        XCTAssertEqual(overlay.wrists.map(rounded), [CGPoint(x: 0.6, y: CGFloat(Landmarks.restY))].map(rounded))
        XCTAssertNil(overlay.restY)
    }

    func testNoPoseMeansNoShoulders() throws {
        let frame = try LandmarkFrame(timestamp: 0, imageSize: ImageSize(width: 10, height: 20))

        let overlay = BodyOverlay(frame: frame, restY: nil)

        XCTAssertEqual(overlay.shoulders, [])
        XCTAssertEqual(overlay.wrists, [])
        XCTAssertEqual(overlay.imageSize, CGSize(width: 10, height: 20))
    }

    /// Landmarks are Float; compare at 4 decimals.
    private func rounded(_ point: CGPoint) -> CGPoint {
        CGPoint(x: (point.x * 10_000).rounded() / 10_000, y: (point.y * 10_000).rounded() / 10_000)
    }
}
