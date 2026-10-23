import RecognitionCore
import XCTest

final class ClipQualityTests: XCTestCase {
    func testFractionsCountFramesWithBodyAndWithAnyHand() {
        // 10 frames: 6 with body; one frame with two hands and one with one hand
        var frames = Array(repeating: ClipQuality.Frame(body: true, handCount: 0), count: 6)
        frames += Array(repeating: ClipQuality.Frame(body: false, handCount: 0), count: 2)
        frames[0].handCount = 2
        frames[6].handCount = 1
        frames += [ClipQuality.Frame(body: false, handCount: 0), ClipQuality.Frame(body: false, handCount: 0)]

        let quality = ClipQuality.from(frames: frames)

        XCTAssertEqual(quality.poseFraction, 0.6, accuracy: 1e-12)
        XCTAssertEqual(quality.handFraction, 0.2, accuracy: 1e-12)
    }

    func testFullyTrackedClipScoresOne() {
        let quality = ClipQuality.from(frames: Array(repeating: .init(body: true, handCount: 1), count: 5))

        XCTAssertEqual(quality, ClipQuality(poseFraction: 1, handFraction: 1))
    }

    func testEmptyClipHasNoEvidence() {
        XCTAssertEqual(ClipQuality.from(frames: []), ClipQuality(poseFraction: 0, handFraction: 0))
    }
}
