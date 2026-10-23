import Foundation

/// Plays the PLAN §1 clinic call on timers so the whole demo can be clicked
/// through in the simulator without a backend, a camera or a real call.
@MainActor
final class FakeCallDriver: CallDriver {
    struct Options: Sendable {
        /// Multiply every delay; below 1 runs the script faster.
        var timeScale: Double = 1
        /// Script stages (0-based) whose first approval comes back "not delivered",
        /// as when the receptionist is still talking (ledger B24).
        var undeliveredStages: Set<Int> = []
    }

    let events: AsyncStream<CallEvent>

    private let continuation: AsyncStream<CallEvent>.Continuation
    private let options: Options
    private let stages: [DemoScript.Stage]
    private var nextStage = 0
    private var approvedTurns: Set<TurnID> = []
    private var failedStages: Set<Int> = []
    private var speakingTurn: TurnID?
    private var speakingTask: Task<Void, Never>?
    private var tasks: [Task<Void, Never>] = []
    private var isOver = false

    init(options: Options = Options(), stages: [DemoScript.Stage] = DemoScript.stages) {
        (events, continuation) = AsyncStream.makeStream(of: CallEvent.self)
        self.options = options
        self.stages = stages
    }

    // MARK: CallDriver

    func start(_ setup: CallSetup) {
        schedule(after: 0) { $0.emit(.status(.dialing)) }
        schedule(after: 1) { $0.emit(.status(.ringing)) }
        schedule(after: 2.5) { driver in
            driver.emit(.status(.inCall))
            driver.emit(.camera(.watching))
            driver.playNextStage()
        }
    }

    func updateChips(turnID: TurnID, words: [String]) {
        guard !words.isEmpty else { return }
        let draft = DemoScript.draft(for: words)
        schedule(after: 0.5) {
            $0.emit(.draft(turnID: turnID, text: draft.text, source: draft.source))
        }
    }

    func approve(turnID: TurnID, text: String) {
        guard !isOver, speakingTurn == nil, approvedTurns.insert(turnID).inserted else { return }
        speakingTurn = turnID
        emit(.status(.speaking))
        let stage = nextStage - 1
        let shouldFail = options.undeliveredStages.contains(stage) && failedStages.insert(stage).inserted
        let duration = max(1.5, Double(text.count) * 0.06)
        speakingTask = schedule(after: duration) { driver in
            driver.finishSpeaking(turnID: turnID, delivered: !shouldFail)
        }
    }

    func stop() {
        guard let turnID = speakingTurn else { return }
        speakingTask?.cancel()
        finishSpeaking(turnID: turnID, delivered: false)
    }

    func end() {
        guard !isOver else { return }
        emit(.status(.ended))
        isOver = true
        tasks.forEach { $0.cancel() }
        tasks.removeAll()
        continuation.finish()
    }

    // MARK: Script

    private func finishSpeaking(turnID: TurnID, delivered: Bool) {
        speakingTurn = nil
        speakingTask = nil
        if delivered {
            emit(.spoken(turnID: turnID))
        } else {
            emit(.notDelivered(turnID: turnID))
        }
        emit(.status(.inCall))
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
            schedule(after: at) { $0.emit(.caption(text: caption, at: .now)) }
            at += 2.5
        }
        if stage.losesFraming {
            schedule(after: at) { $0.emit(.camera(.cantSee)) }
            at += 1.5
            schedule(after: at) { $0.emit(.camera(.watching)) }
            at += 1
        }
        for sign in stage.signs {
            schedule(after: at) { $0.emit(.camera(.signing)) }
            at += 1.2
            schedule(after: at) { driver in
                driver.emit(.recognition(sign))
                driver.emit(.camera(.watching))
            }
            at += 1
        }
    }

    private func emit(_ event: CallEvent) {
        guard !isOver else { return }
        continuation.yield(event)
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
