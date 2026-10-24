import AVFoundation
import XCTest
@testable import Ishara

/// Which camera view each run shows, and where tracked points land on the preview.
@MainActor
final class CameraCardTests: XCTestCase {
    private func camera(_ permission: CameraPermission, unavailable: Bool = false) -> LiveCamera {
        let camera = LiveCamera(session: AVCaptureSession(), permission: permission)
        camera.isUnavailable = unavailable
        return camera
    }

    func testWithoutALiveCameraThePlaceholderStays() {
        XCTAssertEqual(CameraCardContent.content(for: nil, isSimulator: true), .placeholder(.simulator))
        XCTAssertEqual(CameraCardContent.content(for: nil, isSimulator: false), .placeholder(.cameraOff))
    }

    func testALiveCameraIsPreviewedOnceAllowedOrWhileAsking() {
        XCTAssertEqual(CameraCardContent.content(for: camera(.authorized), isSimulator: false), .live)
        XCTAssertEqual(CameraCardContent.content(for: camera(.notDetermined), isSimulator: false), .live,
                       "the system prompt shows over the preview on Get ready")
    }

    func testRefusedOrBlockedCameraExplainsWhy() {
        XCTAssertEqual(CameraCardContent.content(for: camera(.denied), isSimulator: false), .blocked(.denied))
        XCTAssertEqual(CameraCardContent.content(for: camera(.restricted), isSimulator: false), .blocked(.restricted))
    }

    func testMissingFrontCameraShowsAPlaceholderEvenWhenAllowed() {
        XCTAssertEqual(CameraCardContent.content(for: camera(.authorized, unavailable: true), isSimulator: false),
                       .placeholder(.noCamera))
    }

    func testScriptedRecognitionAndFixturesShowThePlaceholder() throws {
        let fixture = try XCTUnwrap(DemoFixture.signing.makeActiveCall())

        XCTAssertEqual(CameraCardContent.content(for: fixture.recognition.camera, isSimulator: true),
                       .placeholder(.simulator))
        XCTAssertEqual(CameraCardContent.content(for: ScriptedRecognitionController().camera, isSimulator: false),
                       .placeholder(.cameraOff))
    }

    func testPlaceholderCopyIsForTheUser() {
        XCTAssertEqual(CameraPlaceholder.simulator.message, "Camera preview appears on your iPhone.")
        XCTAssertEqual(CameraPlaceholder.cameraOff.message, "Camera is off in demo mode.")
        XCTAssertEqual(CameraPlaceholder.noCamera.message, "No front camera found on this iPhone.")
    }

    // MARK: Mapping tracked points onto the preview

    private let portrait = CGSize(width: 720, height: 1280)

    func testSameAspectMapsStraightAcrossButMirrored() {
        let mapping = PreviewMapping(imageSize: portrait, viewSize: CGSize(width: 360, height: 640))

        XCTAssertEqual(mapping.point(CGPoint(x: 0.25, y: 0.5)), CGPoint(x: 270, y: 320),
                       "the signer's left side shows on the right, like a mirror")
    }

    func testUnmirroredKeepsTheSide() {
        let mapping = PreviewMapping(imageSize: portrait, viewSize: CGSize(width: 360, height: 640), mirrored: false)

        XCTAssertEqual(mapping.point(CGPoint(x: 0.25, y: 0.5)), CGPoint(x: 90, y: 320))
    }

    func testWideCardCropsTopAndBottom() {
        // 720×1280 filled into 360×170: scaled to 360×640, 235 pt cut off above and below.
        let mapping = PreviewMapping(imageSize: portrait, viewSize: CGSize(width: 360, height: 170))

        XCTAssertEqual(mapping.point(CGPoint(x: 0.5, y: 0.5)), CGPoint(x: 180, y: 85))
        XCTAssertEqual(mapping.y(0.4), 21, accuracy: 0.001)
        XCTAssertEqual(mapping.point(CGPoint(x: 1, y: 0)), CGPoint(x: 0, y: -235))
    }

    func testTallCardCropsTheSides() {
        // 720×1280 filled into 100×400: scaled to 225×400, 62.5 pt cut off left and right.
        let mapping = PreviewMapping(imageSize: portrait, viewSize: CGSize(width: 100, height: 400))

        XCTAssertEqual(mapping.point(CGPoint(x: 0.5, y: 0.25)), CGPoint(x: 50, y: 100))
        XCTAssertEqual(mapping.point(CGPoint(x: 1, y: 1)), CGPoint(x: -62.5, y: 400))
    }
}
