import AVFoundation
import SignPipeline
import XCTest
@testable import Ishara

/// Camera permission and session sharing, without ever opening the camera or showing
/// the system prompt.
@MainActor
final class CameraFeedTests: XCTestCase {
    func testPermissionStatesMapForTheScreens() {
        XCTAssertEqual(CameraPermission(.notDetermined), .notDetermined)
        XCTAssertEqual(CameraPermission(.authorized), .authorized)
        XCTAssertEqual(CameraPermission(.denied), .denied)
        XCTAssertEqual(CameraPermission(.restricted), .restricted)
        XCTAssertEqual(CameraPermission(AVAuthorizationStatus(rawValue: 99)!), .denied,
                       "an unknown future status must not count as allowed")
    }

    func testPreviewUsesTheSessionRecognitionReadsFrom() throws {
        let source = CameraFrameSource()
        let feed = CameraFeed(source: source, access: FakeAccess(.denied).access)
        let recognition = PipelineRecognitionController(feed: feed) { throw CancellationError() }

        let camera = try XCTUnwrap(recognition.camera)
        XCTAssertTrue(camera.session === source.captureSession, "the preview must not open a second session")
        XCTAssertTrue(recognition.camera === feed.camera)
        XCTAssertTrue(feed.camera === feed.camera, "every screen shows the same camera")
    }

    func testStartsWithTheCurrentPermission() {
        XCTAssertEqual(CameraFeed(access: FakeAccess(.authorized).access).camera?.permission, .authorized)
        XCTAssertEqual(CameraFeed(access: FakeAccess(.restricted).access).camera?.permission, .restricted)
    }

    func testRefusedCameraGivesNoFramesAndIsNotReportedAsAFailure() async {
        let access = FakeAccess(.denied)
        let source = CameraFrameSource()
        let feed = CameraFeed(source: source, access: access.access)
        var failures: [Error] = []
        feed.onFailure = { failures.append($0) }

        var received = 0
        for await _ in feed.items() { received += 1 }

        XCTAssertEqual(received, 0)
        XCTAssertEqual(feed.camera?.permission, .denied)
        XCTAssertEqual(access.requests, 0, "a refused camera must not prompt again")
        XCTAssertTrue(failures.isEmpty, "the camera card explains a refusal; it isn't a recognition failure")
        XCTAssertTrue(source.captureSession.inputs.isEmpty, "the camera was opened without permission")
    }

    func testAsksOnceWhenNotAskedYetThenShowsTheAnswer() async {
        let access = FakeAccess(.notDetermined, afterRequest: .denied)
        let feed = CameraFeed(access: access.access)
        XCTAssertEqual(feed.camera?.permission, .notDetermined)

        for await _ in feed.items() {}

        XCTAssertEqual(access.requests, 1)
        XCTAssertEqual(feed.camera?.permission, .denied)
    }

    func testRestrictedCameraIsNotPrompted() async {
        let access = FakeAccess(.restricted)
        let feed = CameraFeed(access: access.access)

        for await _ in feed.items() {}

        XCTAssertEqual(access.requests, 0)
        XCTAssertEqual(feed.camera?.permission, .restricted)
    }

    func testSavedVideosAndReplayedResultsHaveNoLiveCamera() {
        XCTAssertNil(ClipFeed(clips: []).camera)
        XCTAssertNil(ScriptedRecognitionController().camera)
        XCTAssertNil(PipelineRecognitionController(feed: ClipFeed(clips: [])) { throw CancellationError() }.camera)
    }
}

/// Camera permission that answers from a script. `requests` counts system prompts.
private final class FakeAccess: @unchecked Sendable {
    private let lock = NSLock()
    private var status: AVAuthorizationStatus
    private let afterRequest: AVAuthorizationStatus?
    private var requestCount = 0

    init(_ status: AVAuthorizationStatus, afterRequest: AVAuthorizationStatus? = nil) {
        self.status = status
        self.afterRequest = afterRequest
    }

    var requests: Int { lock.withLock { requestCount } }

    var access: CameraAccess {
        CameraAccess(
            status: { self.lock.withLock { self.status } },
            request: {
                self.lock.withLock {
                    self.requestCount += 1
                    if let next = self.afterRequest { self.status = next }
                }
            })
    }
}
