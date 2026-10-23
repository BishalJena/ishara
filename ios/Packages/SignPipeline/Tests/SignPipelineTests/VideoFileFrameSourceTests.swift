import AVFoundation
import XCTest
@testable import SignPipeline

final class VideoFileFrameSourceTests: XCTestCase {
    private func decode(_ url: URL, pacing: VideoFileFrameSource.Pacing = .asFastAsPossible) async throws
        -> [VideoFrame]
    {
        var frames: [VideoFrame] = []
        for try await frame in VideoFileFrameSource(url: url, pacing: pacing).frames() {
            frames.append(frame)
        }
        return frames
    }

    func testYieldsEveryFrameWithItsTimestampInOrder() async throws {
        let url = try await TestVideo.write(frames: 9, fps: 15)
        defer { try? FileManager.default.removeItem(at: url) }

        let frames = try await decode(url)

        XCTAssertEqual(frames.count, 9)
        for (index, frame) in frames.enumerated() {
            XCTAssertEqual(frame.timestamp.seconds, Double(index) / 15, accuracy: 1e-6, "frame \(index)")
            XCTAssertEqual(TestVideo.meanLevel(of: frame.pixelBuffer), Double(TestVideo.level(ofFrame: index)),
                           accuracy: 6, "frame \(index) content")
        }
    }

    func testDecodesToBGRAAtTheStoredSizeAndUprightOrientation() async throws {
        let url = try await TestVideo.write(frames: 2, fps: 30, width: 64, height: 48)
        defer { try? FileManager.default.removeItem(at: url) }

        let decoded = try await decode(url)
        let frame = try XCTUnwrap(decoded.first)

        XCTAssertEqual(CVPixelBufferGetPixelFormatType(frame.pixelBuffer), kCVPixelFormatType_32BGRA)
        XCTAssertEqual(frame.orientation, .up)
        XCTAssertEqual(frame.uprightSize, ImageSize(width: 64, height: 48))
    }

    func testPortraitRecordingReportsRotationAndUprightSize() async throws {
        let portrait = CGAffineTransform(a: 0, b: 1, c: -1, d: 0, tx: 48, ty: 0)
        let url = try await TestVideo.write(frames: 2, fps: 30, width: 64, height: 48, transform: portrait)
        defer { try? FileManager.default.removeItem(at: url) }

        let decoded = try await decode(url)
        let frame = try XCTUnwrap(decoded.first)

        XCTAssertEqual(frame.orientation, .right)
        XCTAssertEqual(frame.uprightSize, ImageSize(width: 48, height: 64))
    }

    func testRealTimePacingTakesAboutTheClipDuration() async throws {
        let url = try await TestVideo.write(frames: 6, fps: 10)
        defer { try? FileManager.default.removeItem(at: url) }

        let clock = ContinuousClock()
        let started = clock.now
        let frames = try await decode(url, pacing: .realTime)
        let elapsed = clock.now - started

        XCTAssertEqual(frames.count, 6)
        XCTAssertGreaterThan(elapsed, .milliseconds(450), "last frame is due 0.5 s after the first")
    }

    func testMissingFileFails() async {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("absent-\(UUID().uuidString).mov")
        do {
            _ = try await decode(url)
            XCTFail("expected an error")
        } catch {}
    }
}
