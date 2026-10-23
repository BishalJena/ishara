import XCTest
@testable import SignPipeline

final class EncoderInputTests: XCTestCase {
    private func frames(_ count: Int) -> [[Float]] {
        (0..<count).map { frame in
            (0..<609).map { Float(frame + 1) + Float($0) / 1000 }
        }
    }

    func testShapesFollowTheCoreMLContract() {
        XCTAssertEqual(EncoderInput.featureShape, [1, 256, 609])
        XCTAssertEqual(EncoderInput.maskShape, [1, 256])
    }

    func testCopiesFramesInOrderAndZeroPadsTheRest() throws {
        let source = frames(5)
        let input = try EncoderInput(frames: source)

        XCTAssertEqual(input.frameCount, 5)
        XCTAssertEqual(input.features.count, 256 * 609)
        for (index, frame) in source.enumerated() {
            XCTAssertEqual(Array(input.features[index * 609..<(index + 1) * 609]), frame)
        }
        XCTAssertTrue(input.features[(5 * 609)...].allSatisfy { $0 == 0 })
    }

    func testMaskMarksRealFramesThenPadding() throws {
        let input = try EncoderInput(frames: frames(7))
        XCTAssertEqual(input.mask.count, 256)
        XCTAssertEqual(Array(input.mask[..<7]), Array(repeating: 1, count: 7))
        XCTAssertEqual(Array(input.mask[7...]), Array(repeating: 0, count: 249))
    }

    func testAcceptsExactly256FramesWithoutPadding() throws {
        let input = try EncoderInput(frames: frames(256))
        XCTAssertEqual(input.mask, Array(repeating: 1, count: 256))
        XCTAssertEqual(Array(input.features.suffix(609)), frames(256)[255])
    }

    func testRejects257FramesInsteadOfTruncating() {
        XCTAssertThrowsError(try EncoderInput(frames: frames(257))) {
            XCTAssertEqual($0 as? EncoderInputError, .tooManyFrames(257))
        }
    }

    func testRejectsFewerThanFourFramesButAcceptsFour() {
        XCTAssertThrowsError(try EncoderInput(frames: frames(3))) {
            XCTAssertEqual($0 as? EncoderInputError, .tooFewFrames(3))
        }
        XCTAssertNoThrow(try EncoderInput(frames: frames(4)))
    }

    func testRejectsFrameOfWrongWidth() {
        var source = frames(4)
        source[2].removeLast()
        XCTAssertThrowsError(try EncoderInput(frames: source)) {
            XCTAssertEqual($0 as? EncoderInputError, .wrongFrameWidth(frame: 2, count: 608))
        }
    }

    func testRejectsNonFiniteFeature() {
        var source = frames(4)
        source[1][100] = .infinity
        XCTAssertThrowsError(try EncoderInput(frames: source)) {
            XCTAssertEqual($0 as? EncoderInputError, .nonFiniteFeature(frame: 1))
        }
    }
}
