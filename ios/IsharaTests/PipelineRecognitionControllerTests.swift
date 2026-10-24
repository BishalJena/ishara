import AVFoundation
import RecognitionCore
import SignPipeline
import XCTest
@testable import Ishara

/// The real recognition controller with a stub landmark provider and a fixed encoder:
/// frames → checklist + calibration → detector → classifier → events for the call screen.
@MainActor
final class PipelineRecognitionControllerTests: XCTestCase {
    private var collected: [RecognitionEvent] = []
    private var listener: Task<Void, Never>?

    override func tearDown() async throws {
        listener?.cancel()
    }

    private func makeController(
        _ landmarks: [LandmarkFrame],
        extra: [FeedItem] = [],
        embedding: [Float] = [0.99, 0.05, 0, 0],
        bundle: RecognitionBundle? = testBundle,
        camera: LiveCamera? = nil
    ) -> PipelineRecognitionController {
        let items = videoFrames(for: landmarks).map(FeedItem.frame) + extra
        let feed = ScriptedFeed(items)
        feed.camera = camera
        let controller = PipelineRecognitionController(feed: feed) {
            PipelineComponents(
                landmarks: ScriptedLandmarkProvider(landmarks),
                classifier: SegmentClassifier(
                    encoder: SignEncoder(model: FixedEmbeddingModel(embedding)),
                    matcher: bundle.map(SignMatcher.init)))
        }
        let events = controller.signingEvents()
        listener = Task { for await event in events { self.collected.append(event) } }
        return controller
    }

    private var results: [RecognitionResult] {
        collected.compactMap { if case .result(let result) = $0 { result } else { nil } }
    }

    func testAcceptedSignBecomesAChip() async {
        let controller = makeController(Landmarks.calibratedStream { Landmarks.sign(from: $0) })

        controller.start()

        let shown = await eventually { self.results == [.sign(.hello)] }
        XCTAssertTrue(shown)
        XCTAssertTrue(controller.getReady.isReady, "checklist and calibration came from the frames")
        XCTAssertTrue(collected.contains(.camera(.signing)))
    }

    func testLowConfidenceSignBecomesAQuestionMark() async {
        let controller = makeController(
            Landmarks.calibratedStream { Landmarks.sign(from: $0) }, embedding: [0.7, 0.7, 0, 0])

        controller.start()

        let shown = await eventually { self.results == [.unsure] }
        XCTAssertTrue(shown)
    }

    func testWithoutARecognitionBundleEverySignIsAQuestionMark() async {
        let controller = makeController(
            Landmarks.calibratedStream { Landmarks.sign(from: $0) }, bundle: nil)

        controller.start()

        let shown = await eventually { self.results == [.unsure] }
        XCTAssertTrue(shown)
    }

    func testRejectedAttemptProducesNothing() async {
        let controller = makeController(Landmarks.calibratedStream { Landmarks.lostMidSign(from: $0) })

        controller.start()

        let sawRedPill = await eventually { self.collected.contains(.camera(.cantSee)) && self.collected.last == .camera(.watching) }
        XCTAssertTrue(sawRedPill)
        try? await Task.sleep(for: .milliseconds(100))
        XCTAssertEqual(results, [])
    }

    func testHoldAfterAReplayedClipLetsTheSignFinish() async {
        let clip = Landmarks.calibratedStream { start in
            Landmarks.run(from: start, seconds: 0.8, wristY: Landmarks.signingY)
                + Landmarks.run(from: start + 0.8, seconds: 0.1)
        }
        let controller = makeController(clip, extra: [.hold(seconds: 0.8)])

        controller.start()

        let shown = await eventually { self.results == [.sign(.hello)] }
        XCTAssertTrue(shown)
    }

    func testWithoutTheHoldAClipEndingTooSoonStaysOpen() async {
        let clip = Landmarks.calibratedStream { start in
            Landmarks.run(from: start, seconds: 0.8, wristY: Landmarks.signingY)
                + Landmarks.run(from: start + 0.8, seconds: 0.1)
        }
        let controller = makeController(clip)

        controller.start()

        let signing = await eventually { self.collected.last == .camera(.signing) }
        XCTAssertTrue(signing)
        try? await Task.sleep(for: .milliseconds(100))
        XCTAssertEqual(results, [])
    }

    func testPreviewShowsTheLatestTrackedBodyAndTheRestLine() async throws {
        let camera = LiveCamera(session: AVCaptureSession())
        let controller = makeController(Landmarks.calibratedStream { Landmarks.sign(from: $0) }, camera: camera)

        controller.start()

        let shown = await eventually { self.results == [.sign(.hello)] }
        XCTAssertTrue(shown)
        let overlay = try XCTUnwrap(camera.overlay)
        XCTAssertEqual(overlay.imageSize, CGSize(width: 720, height: 1280))
        XCTAssertEqual(overlay.wrists.map(\.y), [CGFloat(Landmarks.restY), CGFloat(Landmarks.restY)],
                       "the last frame has both hands back at rest")
        XCTAssertEqual(overlay.shoulders.count, 2)
        XCTAssertNotNil(overlay.restY, "calibration finished, so the rest line is known")
    }

    func testOverlayHasNoRestLineUntilCalibrated() async {
        let landmarks = Landmarks.calibratedStream { _ in [] }
        let components = PipelineComponents(
            landmarks: InOrderLandmarkProvider(landmarks),
            classifier: SegmentClassifier(encoder: nil, matcher: nil))
        let items = AsyncStream<FeedItem> { continuation in
            videoFrames(for: landmarks).forEach { continuation.yield(.frame($0)) }
            continuation.yield(.hold(seconds: 0.1))
            continuation.finish()
        }

        let overlays = await Task.detached {
            var overlays: [BodyOverlay] = []
            await PipelineRecognitionController.process(items, with: components) { output in
                if case .overlay(let overlay) = output { overlays.append(overlay) }
            }
            return overlays
        }.value

        XCTAssertEqual(overlays.count, landmarks.count, "one overlay per camera frame, none for held frames")
        XCTAssertNil(overlays.first?.restY)
        XCTAssertNotNil(overlays.last?.restY)
    }

    func testHeldFramesRepeatTheLastFrameAt30fps() {
        let held = PipelineRecognitionController.held(after: Landmarks.frame(t: 1), for: 0.1)

        XCTAssertEqual(held.map { ($0.timestamp * 1000).rounded() }, [1033, 1067, 1100])
    }

    func testSetupFailureIsReported() async {
        struct NoModel: Error {}
        let controller = PipelineRecognitionController(feed: ScriptedFeed([])) { throw NoModel() }

        controller.start()

        let failed = await eventually { controller.failure != nil }
        XCTAssertTrue(failed)
    }

    func testANewCallScreenStreamFinishesTheOldOne() async {
        let controller = PipelineRecognitionController(feed: ScriptedFeed([])) { throw CancellationError() }
        let first = controller.signingEvents()
        _ = controller.signingEvents()

        var iterator = first.makeAsyncIterator()
        let next = await iterator.next()

        XCTAssertNil(next)
    }

    func testStopEndsFramesAndTheStream() async {
        let feed = ScriptedFeed([])
        let controller = PipelineRecognitionController(feed: feed) { throw CancellationError() }
        let events = controller.signingEvents()

        controller.stop()

        var iterator = events.makeAsyncIterator()
        let next = await iterator.next()
        XCTAssertNil(next)
        XCTAssertEqual(feed.stopCount, 1)
    }

    func testReplayGoesToTheFeed() {
        let feed = ScriptedFeed([])
        feed.replayOptions = ["hello_01"]
        let controller = PipelineRecognitionController(feed: feed) { throw CancellationError() }

        controller.replay("hello_01")

        XCTAssertEqual(controller.replayOptions, ["hello_01"])
        XCTAssertEqual(feed.replayed, ["hello_01"])
    }
}

/// Hands out the prepared landmarks one per frame, whatever the frame's timestamp.
private final class InOrderLandmarkProvider: LandmarkProvider {
    private var remaining: ArraySlice<LandmarkFrame>

    init(_ frames: [LandmarkFrame]) { remaining = frames[...] }

    func landmarks(for frame: VideoFrame) throws -> LandmarkFrame {
        try XCTUnwrap(remaining.popFirst())
    }
}
