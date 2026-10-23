import XCTest
@testable import SignPipeline

final class ClipBufferTests: XCTestCase {
    func testBuildsEncoderInputFromCollectedFrames() throws {
        var buffer = ClipBuffer()
        let clip = (0..<6).map { Synthetic.frame(timestamp: Double($0) / 30) }
        clip.forEach { XCTAssertTrue(buffer.append($0)) }

        let input = try buffer.makeEncoderInput()
        let expected = try EncoderInput(frames: FeatureBuilder.features(for: clip))
        XCTAssertEqual(input, expected)
        XCTAssertEqual(input.frameCount, 6)
    }

    func testRejectsClipLongerThan256FramesAndStopsStoring() {
        var buffer = ClipBuffer()
        for index in 0..<256 {
            XCTAssertTrue(buffer.append(Synthetic.frame(timestamp: Double(index))))
        }
        XCTAssertFalse(buffer.hasOverflowed)
        XCTAssertNoThrow(try buffer.makeEncoderInput())

        XCTAssertFalse(buffer.append(Synthetic.frame(timestamp: 256)))
        XCTAssertFalse(buffer.append(Synthetic.frame(timestamp: 257)))
        XCTAssertTrue(buffer.hasOverflowed)
        XCTAssertEqual(buffer.frames.count, 256)
        XCTAssertEqual(buffer.receivedCount, 258)
        XCTAssertThrowsError(try buffer.makeEncoderInput()) {
            XCTAssertEqual($0 as? EncoderInputError, .tooManyFrames(258))
        }
    }

    func testResetStartsAFreshClip() throws {
        var buffer = ClipBuffer()
        (0..<300).forEach { buffer.append(Synthetic.frame(timestamp: Double($0))) }
        buffer.reset()

        XCTAssertEqual(buffer.receivedCount, 0)
        XCTAssertTrue(buffer.frames.isEmpty)
        (0..<4).forEach { buffer.append(Synthetic.frame(timestamp: Double($0))) }
        XCTAssertEqual(try buffer.makeEncoderInput().frameCount, 4)
    }
}
