#if os(iOS)
import CoreMedia
import CoreVideo
import SignPipeline
import SignPipelineMediaPipe
import UIKit
import XCTest

/// Runs the real Holistic Landmarker on MediaPipe's own Holistic test photo and
/// checks the adapter against MediaPipe's expected result for it.
final class HolisticLandmarkProviderTests: XCTestCase {
    /// MediaPipe's iOS Holistic test uses the same tolerance for x and y.
    private let tolerance: Float = 0.03

    func testMapsBodyFaceAndHandsOfTheReferencePhoto() throws {
        let provider = try makeProvider()
        let frame = try provider.landmarks(for: VideoFrame(pixelBuffer: try uprightPhoto(), timestamp: .zero))

        XCTAssertEqual(frame.imageSize, ImageSize(width: 638, height: 1000))
        let pose = try XCTUnwrap(frame.pose, "pose not detected")
        let face = try XCTUnwrap(frame.face, "face not detected")
        let leftHand = try XCTUnwrap(frame.leftHand, "left hand not detected")
        let rightHand = try XCTUnwrap(frame.rightHand, "right hand not detected")
        XCTAssertEqual(face.count, 478, "face mesh plus 10 iris points")

        try assertMatchesExpectedResult(pose: pose, leftHand: leftHand, rightHand: rightHand)
        XCTAssertTrue(frame.hasTrackedShoulders)
        for (index, point) in pose.enumerated() {
            let visibility = try XCTUnwrap(point.visibility, "pose \(index) lost its visibility")
            XCTAssertTrue((0...1).contains(visibility), "pose \(index) visibility \(visibility) is not a probability")
        }
        XCTAssertTrue((face + leftHand + rightHand).allSatisfy { $0.visibility == nil })
    }

    func testRotatedFrameYieldsUprightCoordinates() throws {
        let provider = try makeProvider()
        // Stored sideways, as a portrait camera frame is; `.right` turns it upright.
        let sideways = try rotatedCounterclockwise(try uprightPhoto())
        let frame = try provider.landmarks(for: VideoFrame(pixelBuffer: sideways, timestamp: .zero, orientation: .right))

        XCTAssertEqual(frame.imageSize, ImageSize(width: 638, height: 1000))
        try assertMatchesExpectedResult(
            pose: try XCTUnwrap(frame.pose, "pose not detected"),
            leftHand: try XCTUnwrap(frame.leftHand, "left hand not detected"),
            rightHand: try XCTUnwrap(frame.rightHand, "right hand not detected")
        )
    }

    func testRejectsTimestampsThatDoNotIncrease() throws {
        let provider = try makeProvider()
        let buffer = try uprightPhoto()
        let second = CMTime(value: 1, timescale: 1)
        _ = try provider.landmarks(for: VideoFrame(pixelBuffer: buffer, timestamp: second))

        XCTAssertThrowsError(try provider.landmarks(for: VideoFrame(pixelBuffer: buffer, timestamp: second))) {
            XCTAssertEqual($0 as? HolisticLandmarkProviderError, .nonIncreasingTimestamp(1000, previous: 1000))
        }
        XCTAssertNoThrow(try provider.landmarks(for: VideoFrame(
            pixelBuffer: buffer, timestamp: CMTime(value: 1033, timescale: 1000)
        )))
    }

    /// Values from mediapipe/tasks/testdata/vision/male_full_height_hands_result_cpu.pbtxt
    /// at the pinned MediaPipe revision. The subject's left side is on the
    /// image's right, so the left hand sits at the left wrist (pose 15).
    private func assertMatchesExpectedResult(
        pose: [Landmark], leftHand: [Landmark], rightHand: [Landmark],
        file: StaticString = #filePath, line: UInt = #line
    ) throws {
        let expectedPose: [Int: (x: Float, y: Float)] = [
            0: (0.51091266, 0.15435366),  // nose
            11: (0.6355789, 0.26930806),  // left shoulder
            12: (0.40269345, 0.2746424),  // right shoulder
            15: (0.6036924, 0.39559665),  // left wrist
            16: (0.2462176, 0.49226165),  // right wrist
        ]
        for (index, expected) in expectedPose.sorted(by: { $0.key < $1.key }) {
            assertNear(pose[index], expected, "pose \(index)", file: file, line: line)
        }
        assertNear(leftHand[SignCLIPLayout.wristIndex], (0.6030236, 0.39878464), "left hand wrist", file: file, line: line)
        assertNear(rightHand[SignCLIPLayout.wristIndex], (0.24741295, 0.49643737), "right hand wrist", file: file, line: line)
    }

    private func assertNear(
        _ point: Landmark, _ expected: (x: Float, y: Float), _ name: String, file: StaticString, line: UInt
    ) {
        XCTAssertEqual(point.x, expected.x, accuracy: tolerance, "\(name) x", file: file, line: line)
        XCTAssertEqual(point.y, expected.y, accuracy: tolerance, "\(name) y", file: file, line: line)
    }

    // MARK: - Assets

    private static let assets = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        .appendingPathComponent("TestAssets")

    private func asset(_ name: String) throws -> URL {
        let url = Self.assets.appendingPathComponent(name)
        try XCTSkipUnless(
            FileManager.default.fileExists(atPath: url.path),
            "\(name) is missing; run Scripts/download_holistic_test_assets.sh"
        )
        return url
    }

    private func makeProvider() throws -> HolisticLandmarkProvider {
        try HolisticLandmarkProvider(modelPath: try asset("holistic_landmarker.task").path)
    }

    private func uprightPhoto() throws -> CVPixelBuffer {
        let image = try XCTUnwrap(UIImage(contentsOfFile: try asset("male_full_height_hands.jpg").path)?.cgImage)
        let buffer = try makeBGRABuffer(width: image.width, height: image.height)
        CVPixelBufferLockBaseAddress(buffer, [])
        defer { CVPixelBufferUnlockBaseAddress(buffer, []) }
        let context = try XCTUnwrap(CGContext(
            data: CVPixelBufferGetBaseAddress(buffer),
            width: image.width, height: image.height, bitsPerComponent: 8,
            bytesPerRow: CVPixelBufferGetBytesPerRow(buffer),
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.premultipliedFirst.rawValue | CGBitmapInfo.byteOrder32Little.rawValue
        ))
        context.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
        return buffer
    }

    /// Stored pixel (x, y) shows upright pixel (W - 1 - y, x).
    private func rotatedCounterclockwise(_ upright: CVPixelBuffer) throws -> CVPixelBuffer {
        let width = CVPixelBufferGetWidth(upright)
        let height = CVPixelBufferGetHeight(upright)
        let rotated = try makeBGRABuffer(width: height, height: width)
        CVPixelBufferLockBaseAddress(upright, .readOnly)
        CVPixelBufferLockBaseAddress(rotated, [])
        defer {
            CVPixelBufferUnlockBaseAddress(rotated, [])
            CVPixelBufferUnlockBaseAddress(upright, .readOnly)
        }
        let source = try XCTUnwrap(CVPixelBufferGetBaseAddress(upright)).assumingMemoryBound(to: UInt32.self)
        let target = try XCTUnwrap(CVPixelBufferGetBaseAddress(rotated)).assumingMemoryBound(to: UInt32.self)
        let sourceStride = CVPixelBufferGetBytesPerRow(upright) / 4
        let targetStride = CVPixelBufferGetBytesPerRow(rotated) / 4
        for y in 0..<width {
            for x in 0..<height {
                target[y * targetStride + x] = source[x * sourceStride + (width - 1 - y)]
            }
        }
        return rotated
    }

    private func makeBGRABuffer(width: Int, height: Int) throws -> CVPixelBuffer {
        var buffer: CVPixelBuffer?
        let status = CVPixelBufferCreate(
            nil, width, height, kCVPixelFormatType_32BGRA,
            [kCVPixelBufferIOSurfacePropertiesKey: [:]] as CFDictionary, &buffer
        )
        XCTAssertEqual(status, kCVReturnSuccess)
        return try XCTUnwrap(buffer)
    }
}
#else
import XCTest

final class HolisticLandmarkProviderTests: XCTestCase {
    func testRunsOnlyOnIOS() throws {
        throw XCTSkip("MediaPipeTasksVision ships iOS device and simulator slices only")
    }
}
#endif
