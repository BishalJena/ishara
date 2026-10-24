import Foundation
import Observation
import OSLog
import SignPipeline

let recognitionLog = Logger(subsystem: "ai.ishara.demo", category: "recognition")

/// The parts of the pipeline that run off the main thread. Built inside the worker task,
/// because MediaPipe and Core ML objects aren't safe to share between threads.
struct PipelineComponents {
    var landmarks: any LandmarkProvider
    var classifier: SegmentClassifier
}

/// Real on-device recognition: frames (camera or replayed videos) → holistic landmarks →
/// `RecognitionSession` (checklist, calibration, start/stop detector) → accepted segment →
/// `SegmentClassifier` (SignCLIP + matcher) → chip.
@MainActor
@Observable
final class PipelineRecognitionController: RecognitionController {
    let getReady = GetReadyModel()
    private(set) var failure: String?
    let notice: String?

    @ObservationIgnored private let feed: any FrameFeed
    @ObservationIgnored private let makeComponents: @Sendable () throws -> PipelineComponents
    @ObservationIgnored private var worker: Task<Void, Never>?
    @ObservationIgnored private var continuation: AsyncStream<RecognitionEvent>.Continuation?

    init(
        feed: any FrameFeed,
        notice: String? = nil,
        makeComponents: @escaping @Sendable () throws -> PipelineComponents
    ) {
        self.feed = feed
        self.notice = notice
        self.makeComponents = makeComponents
        feed.onFailure = { [weak self] error in self?.fail(error) }
    }

    var replayOptions: [String] { feed.replayOptions }
    var camera: LiveCamera? { feed.camera }

    func start() {
        guard worker == nil else { return }
        let items = feed.items()
        let makeComponents = makeComponents
        worker = Task.detached { [weak self] in
            let components: PipelineComponents
            do {
                components = try makeComponents()
            } catch {
                await self?.fail(error)
                return
            }
            await Self.process(items, with: components) { output in
                await self?.apply(output)
            }
        }
    }

    func signingEvents() -> AsyncStream<RecognitionEvent> {
        continuation?.finish()
        let (events, continuation) = AsyncStream<RecognitionEvent>.makeStream()
        self.continuation = continuation
        return events
    }

    func replay(_ option: String) {
        feed.replay(option)
    }

    func stop() {
        worker?.cancel()
        worker = nil
        feed.stop()
        continuation?.finish()
        continuation = nil
    }

    // MARK: Worker

    /// What the worker hands back to the main actor.
    enum WorkerOutput: Sendable {
        case session(RecognitionSession.Output)
        case result(RecognitionResult)
    }

    /// Runs the whole pipeline over `items` until the feed finishes or the task is cancelled.
    nonisolated static func process(
        _ items: AsyncStream<FeedItem>,
        with components: PipelineComponents,
        emit: (WorkerOutput) async -> Void
    ) async {
        var session = RecognitionSession()
        var last: LandmarkFrame?
        for await item in items {
            guard !Task.isCancelled else { return }
            let frames: [LandmarkFrame]
            switch item {
            case .frame(let frame):
                do {
                    let landmarks = try components.landmarks.landmarks(for: frame)
                    last = landmarks
                    frames = [landmarks]
                } catch {
                    recognitionLog.info("frame skipped: \(String(describing: error), privacy: .public)")
                    continue
                }
            case .hold(let seconds):
                frames = last.map { held(after: $0, for: seconds) } ?? []
                last = frames.last ?? last
            }
            for frame in frames {
                for output in session.process(frame) {
                    if case .segment(let clip) = output {
                        await emit(.result(components.classifier.classify(clip)))
                    } else {
                        await emit(.session(output))
                    }
                }
            }
        }
    }

    /// The last frame repeated at 30 fps, as if the signer held still.
    nonisolated static func held(after frame: LandmarkFrame, for seconds: Double) -> [LandmarkFrame] {
        let step = 1.0 / 30
        return stride(from: step, through: seconds, by: step).map { offset in
            var copy = frame
            copy.timestamp = frame.timestamp + offset
            return copy
        }
    }

    private func apply(_ output: WorkerOutput) {
        switch output {
        case .session(.passed(let check)):
            getReady.pass(check)
        case .session(.calibrating(let seconds)):
            getReady.recordCalibration(seconds: seconds)
        case .session(.calibrationRestarted):
            getReady.restartCalibration()
        case .session(.calibrated):
            getReady.recordCalibration(seconds: GetReadyModel.calibrationSeconds)
        case .session(.camera(let state)):
            continuation?.yield(.camera(state))
        case .session(.segment):
            break  // classified in the worker
        case .result(let result):
            continuation?.yield(.result(result))
        }
    }

    private func fail(_ error: Error) {
        recognitionLog.error("recognition unavailable: \(String(describing: error), privacy: .public)")
        failure = "Recognition can't start: \(error.localizedDescription)"
    }
}
