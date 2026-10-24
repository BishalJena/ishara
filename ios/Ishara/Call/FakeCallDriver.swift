import CallSession
import Foundation

/// Plays the PLAN §1 clinic call on timers so the whole demo can be clicked through in
/// the simulator without a backend or a real call. It stands in for the backend: it
/// answers the store's messages (chips, approve, stop, end) with the messages the
/// backend would send, so the real `TurnStore` rules apply unchanged.
@MainActor
final class FakeCallDriver: CallDriver, OutgoingMessageSink {
    struct Options: Sendable {
        /// Multiply every delay; below 1 runs the script faster.
        var timeScale: Double = 1
        /// Script stages (0-based) whose first approval comes back "not delivered",
        /// as when the receptionist is still talking (ledger B24).
        var undeliveredStages: Set<Int> = []
    }

    private let options: Options
    private let stages: [DemoScript.Stage]
    /// Plays each stage's signs; nil when real recognition runs alongside the fake call.
    private let recognition: ScriptedRecognitionController?
    private weak var store: TurnStore?
    private var nextStage = 0
    private var approvedTurns: Set<TurnID> = []
    private var failedStages: Set<Int> = []
    private var speakingTurn: TurnID?
    private var speakingTask: Task<Void, Never>?
    private var tasks: [Task<Void, Never>] = []
    private var isOver = false

    /// The fake call never drops its connection, so this never runs.
    var onReconnectStopped: ((ReconnectStop) -> Void)?

    init(
        options: Options = Options(),
        stages: [DemoScript.Stage] = DemoScript.stages,
        recognition: ScriptedRecognitionController? = nil
    ) {
        self.options = options
        self.stages = stages
        self.recognition = recognition
    }

    // MARK: CallDriver

    func start(_ setup: CallSetup) async throws -> TurnStore {
        let store = TurnStore(sink: self, initialState: .dialing)
        self.store = store
        schedule(after: 1) { $0.deliver(.status(.ringing)) }
        schedule(after: 2.5) { driver in
            driver.deliver(.status(.inCall))
            // Turn 0: the agent opens with the disclosure before the user signs.
            driver.deliver(.caption(text: DemoScript.disclosure, at: Date().timeIntervalSince1970, speaker: .agent))
            driver.playNextStage()
        }
        return store
    }

    func close() {
        finish()
    }

    // MARK: OutgoingMessageSink (what the backend would receive)

    func send(_ message: AppMessage) {
        guard !isOver else { return }
        switch message {
        case let .chips(turnID, signs):
            let draft = DemoScript.draft(for: signs)
            schedule(after: 0.5) {
                $0.deliver(.draft(turnID: turnID, text: draft.text, source: draft.source))
            }
        case let .approve(turnID, text):
            approve(turnID: turnID, text: text)
        case .stop:
            guard let turnID = speakingTurn else { return }
            speakingTask?.cancel()
            speakingTask = schedule(after: 0.3) { $0.finishSpeaking(turnID: turnID, delivered: false, reason: "stopped") }
        case .end:
            // The agent says goodbye as it hangs up. The store ignores events once it has
            // ended, so the caption goes in now, while `end()` is still on its way.
            deliver(.caption(text: DemoScript.goodbye, at: Date().timeIntervalSince1970, speaker: .agent))
            finish()
        }
    }

    func discardPending() {}

    // MARK: Script

    private func approve(turnID: TurnID, text: String) {
        // Single use per turn id, like the backend.
        guard speakingTurn == nil, approvedTurns.insert(turnID).inserted else { return }
        speakingTurn = turnID
        // Replies arrive later, never inside the store's own SEND.
        schedule(after: 0) { $0.deliver(.status(.speaking)) }
        let stage = nextStage - 1
        let shouldFail = options.undeliveredStages.contains(stage) && failedStages.insert(stage).inserted
        let duration = max(1.5, Double(text.count) * 0.06)
        speakingTask = schedule(after: duration) { driver in
            driver.finishSpeaking(turnID: turnID, delivered: !shouldFail)
        }
    }

    private func finishSpeaking(turnID: TurnID, delivered: Bool, reason: String = "no_confirmation") {
        speakingTurn = nil
        speakingTask = nil
        deliver(delivered ? .spoken(turnID: turnID) : .notDelivered(turnID: turnID, reason: reason))
        deliver(.status(.inCall))
        if delivered {
            schedule(after: 2) { $0.playNextStage() }
        }
    }

    private func playNextStage() {
        guard nextStage < stages.count else { return }
        let stage = stages[nextStage]
        nextStage += 1

        var at = 0.0
        if let caption = stage.caption {
            schedule(after: at) { $0.deliver(.caption(text: caption, at: Date().timeIntervalSince1970)) }
            at += 2.5
        }
        guard let recognition else { return }
        if stage.losesFraming {
            schedule(after: at) { _ in recognition.emit(.camera(.cantSee)) }
            at += 1.5
            schedule(after: at) { _ in recognition.emit(.camera(.watching)) }
            at += 1
        }
        for sign in stage.signs {
            schedule(after: at) { _ in recognition.sign(sign) }
            at += 2.2
        }
    }

    private func deliver(_ message: ServerMessage) {
        guard !isOver else { return }
        store?.receive(message)
    }

    private func finish() {
        isOver = true
        tasks.forEach { $0.cancel() }
        tasks.removeAll()
    }

    @discardableResult
    private func schedule(after seconds: Double, _ action: @escaping @MainActor (FakeCallDriver) -> Void) -> Task<Void, Never> {
        let delay = seconds * options.timeScale
        let task = Task { [weak self] in
            if delay > 0 {
                try? await Task.sleep(for: .seconds(delay))
            }
            guard !Task.isCancelled, let self else { return }
            action(self)
        }
        tasks.append(task)
        return task
    }
}
