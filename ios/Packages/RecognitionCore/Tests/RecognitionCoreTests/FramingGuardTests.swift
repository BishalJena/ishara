import RecognitionCore
import XCTest

final class FramingGuardTests: XCTestCase {
    private typealias Hand = FramingGuard.Hand

    private let inside = Hand(tracked: true, wristX: 0.5, wristY: 0.5)
    private let resting = Hand(tracked: false, wristX: 0.5, wristY: 1.2)
    private let offRight = Hand(tracked: false, wristX: 1.08, wristY: 0.4)

    /// 30 fps frames; `right(i)` gives the right hand at frame i, the left hand rests.
    private func clip(_ count: Int, right: (Int) -> Hand) -> [FramingGuard.Frame] {
        (0..<count).map { FramingGuard.Frame(timestamp: Double($0) / 30, left: resting, right: right($0)) }
    }

    func testHandInsideTheFrameIsFine() {
        XCTAssertFalse(FramingGuard.handLeftFrame(clip(30) { _ in inside }))
    }

    func testHandOffTheSideForHalfASecondLeftTheFrame() {
        let frames = clip(30) { $0 < 10 ? inside : offRight }
        XCTAssertTrue(FramingGuard.handLeftFrame(frames))
    }

    func testABriefSlipOffTheEdgeIsTolerated() {
        // 6 frames at 30 fps = 0.2 s.
        let frames = clip(30) { (10..<16).contains($0) ? offRight : inside }
        XCTAssertFalse(FramingGuard.handLeftFrame(frames))
    }

    func testTheTopEdgeCounts() {
        let frames = clip(30) { $0 < 10 ? inside : Hand(tracked: false, wristX: 0.5, wristY: -0.05) }
        XCTAssertTrue(FramingGuard.handLeftFrame(frames))
    }

    func testHandsDroppingBelowTheBottomAreResting() {
        let frames = clip(30) { $0 < 10 ? inside : resting }
        XCTAssertFalse(FramingGuard.handLeftFrame(frames))
    }

    func testAHandThatNeverTookPartIsIgnored() {
        let frames = (0..<30).map { FramingGuard.Frame(timestamp: Double($0) / 30, left: offRight, right: inside) }
        XCTAssertFalse(FramingGuard.handLeftFrame(frames))
    }

    func testAMissingHandWithoutAPoseIsNotBlamedOnFraming() {
        let frames = clip(30) { $0 < 10 ? inside : Hand(tracked: false) }
        XCTAssertFalse(FramingGuard.handLeftFrame(frames))
    }

    func testSeparateShortSlipsDoNotAddUp() {
        let frames = clip(40) { (5..<11).contains($0) || (20..<26).contains($0) ? offRight : inside }
        XCTAssertFalse(FramingGuard.handLeftFrame(frames))
    }
}
