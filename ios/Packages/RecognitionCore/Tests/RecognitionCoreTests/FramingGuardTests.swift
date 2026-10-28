import RecognitionCore
import XCTest

final class FramingGuardTests: XCTestCase {
    private typealias Hand = FramingGuard.Hand

    private let inside = Hand(tracked: true, wristX: 0.5, wristY: 0.5)
    private let resting = Hand(tracked: false, wristX: 0.5, wristY: 1.2)
    private let offRight = Hand(tracked: false, wristX: 1.08, wristY: 0.4)
    /// The detector's rest line; a binary fraction so the boundary test compares exactly.
    private let restY = 0.75

    /// 30 fps frames; `right(i)` gives the right hand at frame i, the left hand rests.
    private func clip(_ count: Int, right: (Int) -> Hand) -> [FramingGuard.Frame] {
        (0..<count).map { FramingGuard.Frame(timestamp: Double($0) / 30, left: resting, right: right($0)) }
    }

    func testHandInsideTheFrameIsFine() {
        XCTAssertFalse(FramingGuard.handLeftFrame(clip(30) { _ in inside }, restY: restY))
    }

    func testHandOffTheSideForHalfASecondLeftTheFrame() {
        let frames = clip(30) { $0 < 10 ? inside : offRight }
        XCTAssertTrue(FramingGuard.handLeftFrame(frames, restY: restY))
    }

    func testABriefSlipOffTheEdgeIsTolerated() {
        // 6 frames at 30 fps = 0.2 s.
        let frames = clip(30) { (10..<16).contains($0) ? offRight : inside }
        XCTAssertFalse(FramingGuard.handLeftFrame(frames, restY: restY))
    }

    func testTheTopEdgeCounts() {
        let frames = clip(30) { $0 < 10 ? inside : Hand(tracked: false, wristX: 0.5, wristY: -0.05) }
        XCTAssertTrue(FramingGuard.handLeftFrame(frames, restY: restY))
    }

    func testHandsDroppingBelowTheBottomAreResting() {
        let frames = clip(30) { $0 < 10 ? inside : resting }
        XCTAssertFalse(FramingGuard.handLeftFrame(frames, restY: restY))
    }

    func testAHandThatNeverTookPartIsIgnored() {
        let frames = (0..<30).map { FramingGuard.Frame(timestamp: Double($0) / 30, left: offRight, right: inside) }
        XCTAssertFalse(FramingGuard.handLeftFrame(frames, restY: restY))
    }

    func testAMissingHandWithoutAPoseIsNotBlamedOnFraming() {
        let frames = clip(30) { $0 < 10 ? inside : Hand(tracked: false) }
        XCTAssertFalse(FramingGuard.handLeftFrame(frames, restY: restY))
    }

    func testSeparateShortSlipsDoNotAddUp() {
        let frames = clip(40) { (5..<11).contains($0) || (20..<26).contains($0) ? offRight : inside }
        XCTAssertFalse(FramingGuard.handLeftFrame(frames, restY: restY))
    }

    func testAnArmRestingPastTheSideEdgeIsResting() {
        // Portrait 9:16 crop (issue #58): the dropped hand's pose wrist sits at x ≈ -0.1, y ≈ 0.95.
        let frames = clip(30) { $0 < 10 ? inside : Hand(tracked: false, wristX: -0.1, wristY: 0.95) }
        XCTAssertFalse(FramingGuard.handLeftFrame(frames, restY: restY))
    }

    func testTheRestLineItselfCountsAsResting() {
        let onTheLine = clip(30) { $0 < 10 ? inside : Hand(tracked: false, wristX: 1.08, wristY: 0.75) }
        let justAbove = clip(30) { $0 < 10 ? inside : Hand(tracked: false, wristX: 1.08, wristY: 0.74) }
        XCTAssertFalse(FramingGuard.handLeftFrame(onTheLine, restY: restY))
        XCTAssertTrue(FramingGuard.handLeftFrame(justAbove, restY: restY))
    }

    func testOffTheLeftEdgeCounts() {
        let frames = clip(30) { $0 < 10 ? inside : Hand(tracked: false, wristX: -0.3, wristY: 0.6) }
        XCTAssertTrue(FramingGuard.handLeftFrame(frames, restY: restY))
    }
}
