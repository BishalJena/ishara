import AVFoundation
import XCTest
@testable import SignPipeline

final class CameraFrameSourceTests: XCTestCase {
    func testPreviewSharesTheOneSessionBehindFrames() {
        let source = CameraFrameSource()

        XCTAssertTrue(source.captureSession === source.captureSession,
                      "a preview must attach to the session frames() runs, not open a second one")
        XCTAssertFalse(source.captureSession === CameraFrameSource().captureSession)
    }

    func testReadingTheSessionDoesNotTouchTheCamera() {
        let session = CameraFrameSource().captureSession

        XCTAssertTrue(session.inputs.isEmpty, "the camera is only opened by frames()")
        XCTAssertTrue(session.outputs.isEmpty)
        XCTAssertFalse(session.isRunning)
    }
}
