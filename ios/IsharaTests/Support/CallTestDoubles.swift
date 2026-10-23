import CallSession
import Foundation
@testable import Ishara

/// Records every message the store would put on the socket.
@MainActor
final class RecordingSink: OutgoingMessageSink {
    private(set) var sent: [AppMessage] = []
    private(set) var discards = 0

    func send(_ message: AppMessage) { sent.append(message) }
    func discardPending() { discards += 1 }

    var approvals: [AppMessage] {
        sent.filter { if case .approve = $0 { true } else { false } }
    }

    var chipUpdates: [AppMessage] {
        sent.filter { if case .chips = $0 { true } else { false } }
    }

    var stops: Int { sent.filter { $0 == .stop }.count }
    var ends: Int { sent.filter { $0 == .end }.count }
}

/// turn1, turn2, … so tests can name the turn a message belongs to.
@MainActor
final class SequentialTurnIDs {
    private var next = 1
    func make() -> TurnID {
        defer { next += 1 }
        return TurnID("turn\(next)")!
    }
}

func turn(_ n: Int) -> TurnID { TurnID("turn\(n)")! }

/// Hands the view model a store backed by a `RecordingSink`, or fails like the backend.
@MainActor
final class StubCallDriver: CallDriver {
    let sink = RecordingSink()
    let store: TurnStore
    var startError: Error?
    private(set) var startedWith: [CallSetup] = []
    private(set) var closeCount = 0

    init(initialState: CallState = .dialing) {
        let ids = SequentialTurnIDs()
        store = TurnStore(sink: sink, initialState: initialState, makeTurnID: { ids.make() })
    }

    func start(_ setup: CallSetup) async throws -> TurnStore {
        startedWith.append(setup)
        if let startError { throw startError }
        return store
    }

    func close() { closeCount += 1 }
}

/// A recognizer the test drives by hand.
@MainActor
final class StubRecognition: RecognitionController {
    let getReady = GetReadyModel()
    var failure: String?
    var notice: String?
    var replayOptions: [String] = []
    private(set) var startCount = 0
    private(set) var stopCount = 0
    private(set) var replayed: [String] = []
    private var continuation: AsyncStream<RecognitionEvent>.Continuation?

    func start() { startCount += 1 }

    func signingEvents() -> AsyncStream<RecognitionEvent> {
        let (events, continuation) = AsyncStream<RecognitionEvent>.makeStream()
        self.continuation = continuation
        return events
    }

    func replay(_ option: String) { replayed.append(option) }

    func stop() {
        stopCount += 1
        continuation?.finish()
    }

    func emit(_ event: RecognitionEvent) { continuation?.yield(event) }
}

/// Polls `condition` until it holds or `timeout` passes.
@MainActor
func eventually(timeout: Duration = .seconds(2), _ condition: () async -> Bool) async -> Bool {
    let clock = ContinuousClock()
    let deadline = clock.now.advanced(by: timeout)
    while clock.now < deadline {
        if await condition() { return true }
        try? await Task.sleep(for: .milliseconds(5))
    }
    return await condition()
}
