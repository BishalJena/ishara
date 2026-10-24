#if os(iOS)
import CoreMedia
import CoreVideo
import SignPipeline
@testable import SignPipelineMediaPipe
import XCTest

/// MediaPipe's Holistic task only accepts upright images, so the provider turns
/// rotated frames upright itself. Pixels are labelled by their stored position.
final class UprightPixelBufferTests: XCTestCase {
    /// Stored 3 wide × 2 high:
    ///     1 2 3
    ///     4 5 6
    private let stored: [[UInt32]] = [[1, 2, 3], [4, 5, 6]]

    func testUpReturnsTheSameBuffer() throws {
        let buffer = try makeBuffer(stored)
        let upright = try HolisticLandmarkProvider.uprightPixelBuffer(of: frame(buffer, .up))
        XCTAssertTrue(upright === buffer)
    }

    func testRightTurnsClockwise() throws {
        XCTAssertEqual(try upright(.right), [[4, 1], [5, 2], [6, 3]])
    }

    func testLeftTurnsCounterclockwise() throws {
        XCTAssertEqual(try upright(.left), [[3, 6], [2, 5], [1, 4]])
    }

    func testDownTurnsHalfway() throws {
        XCTAssertEqual(try upright(.down), [[6, 5, 4], [3, 2, 1]])
    }

    func testRotatedFrameMustBeBGRA() throws {
        let buffer = try makeBuffer(stored, format: kCVPixelFormatType_32ARGB)
        XCTAssertThrowsError(try HolisticLandmarkProvider.uprightPixelBuffer(of: frame(buffer, .right))) {
            XCTAssertEqual($0 as? HolisticLandmarkProviderError, .unsupportedPixelFormat(kCVPixelFormatType_32ARGB))
        }
    }

    private func upright(_ orientation: FrameOrientation) throws -> [[UInt32]] {
        let input = frame(try makeBuffer(stored), orientation)
        let output = try HolisticLandmarkProvider.uprightPixelBuffer(of: input)
        XCTAssertEqual(CVPixelBufferGetPixelFormatType(output), kCVPixelFormatType_32BGRA)
        XCTAssertEqual(
            ImageSize(width: CVPixelBufferGetWidth(output), height: CVPixelBufferGetHeight(output)),
            input.uprightSize
        )
        return read(output)
    }

    private func frame(_ buffer: CVPixelBuffer, _ orientation: FrameOrientation) -> VideoFrame {
        VideoFrame(pixelBuffer: buffer, timestamp: .zero, orientation: orientation)
    }

    private func makeBuffer(_ rows: [[UInt32]], format: OSType = kCVPixelFormatType_32BGRA) throws -> CVPixelBuffer {
        var buffer: CVPixelBuffer?
        XCTAssertEqual(CVPixelBufferCreate(nil, rows[0].count, rows.count, format, nil, &buffer), kCVReturnSuccess)
        let created = try XCTUnwrap(buffer)
        CVPixelBufferLockBaseAddress(created, [])
        defer { CVPixelBufferUnlockBaseAddress(created, []) }
        let base = try XCTUnwrap(CVPixelBufferGetBaseAddress(created))
        let rowBytes = CVPixelBufferGetBytesPerRow(created)
        for (y, row) in rows.enumerated() {
            let pixels = (base + y * rowBytes).assumingMemoryBound(to: UInt32.self)
            for (x, value) in row.enumerated() { pixels[x] = value }
        }
        return created
    }

    private func read(_ buffer: CVPixelBuffer) -> [[UInt32]] {
        CVPixelBufferLockBaseAddress(buffer, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(buffer, .readOnly) }
        let base = CVPixelBufferGetBaseAddress(buffer)!
        let rowBytes = CVPixelBufferGetBytesPerRow(buffer)
        return (0..<CVPixelBufferGetHeight(buffer)).map { y in
            let pixels = (base + y * rowBytes).assumingMemoryBound(to: UInt32.self)
            return (0..<CVPixelBufferGetWidth(buffer)).map { pixels[$0] }
        }
    }
}
#endif
