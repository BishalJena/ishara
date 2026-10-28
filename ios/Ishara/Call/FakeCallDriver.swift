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
        /// Script stages whose first reply the receptionist talks over while it is being
        /// spoken. Ordinary talk doesn't cut the reply off (docs/WORKFLOW.md), so it is
        /// still delivered.
        var interruptedStages: Set<Int> = []
        /// Lose the backend connection mid-call: on a live call once the first draft is on
        /// screen, on a delegated call once the agent has asked its question.
        var connectionDrop: ConnectionDrop?
    }

    /// How a simulated lost connection plays out, like `LiveCallDriver`'s reconnects.
    enum ConnectionDrop: String, Sendable {
        /// The socket comes back and the backend reports the call status again.
        case reconnects
        /// Every reconnect fails, and the backend stays unreachable (notes too).
        case staysDown
    }

    /// What the receptionist says over the reply in an interrupted stage.
    static let interruption = "Sorry, who's calling?"
    static let dropDelay = 1.5
    static let reconnectDelay = 3.0

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
    /// The simulated connection is down: nothing the app sends arrives.
    private var isDisconnected = false

    // Delegated call (D9), played from `DelegatedDemo`.
    private var setup: CallSetup?
    private var transcript: [TranscriptEntry] = []
    private var answers: [String] = []
    private var openAskID: String?
    private var askTimer: Task<Void, Never>?

    /// Runs only when `Options.connectionDrop` is `.staysDown`.
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
        self.setup = setup
        if let delegation = setup.delegation {
            playDelegated(setup, delegation)
            return store
        }
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

    func createBrief(_ request: BriefRequest) async throws -> Brief {
        DelegatedDemo.brief(for: request)
    }

    func notes() async throws -> CallNotes {
        guard let setup else { throw CallDriverError.noCall }
        if isDisconnected { throw URLError(.cannotConnectToHost) }
        guard let delegation = setup.delegation else {
            return CallNotes(callID: "demo-call", mode: .live, ready: isOver, transcript: transcript)
        }
        return DelegatedDemo.notes(
            goal: delegation.brief.goal, name: setup.details.name, brief: delegation.brief.text,
            transcript: transcript, answers: answers, ready: isOver)
    }

    // MARK: OutgoingMessageSink (what the backend would receive)

    func send(_ message: AppMessage) {
        guard !isOver, !isDisconnected else { return }
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
            say(.agent, DemoScript.goodbye)
            finish()
        case let .answer(askID, choice):
            answer(askID: askID, choice: choice)
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
        if options.interruptedStages.contains(stage) {
            schedule(after: duration / 2) { $0.deliver(.caption(text: Self.interruption, at: Date().timeIntervalSince1970)) }
        }
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
        // The first turn's chips and draft are on screen by now.
        if nextStage == 1, let drop = options.connectionDrop {
            schedule(after: at) { $0.loseConnection(drop) }
        }
    }

    /// The app's socket goes away. The backend side of the call carries on (the delegated
    /// question's timer keeps running), but nothing reaches the app and nothing the app
    /// sends arrives, until the socket comes back or the app gives up.
    private func loseConnection(_ drop: ConnectionDrop) {
        isDisconnected = true
        store?.connectionLost()
        switch drop {
        case .reconnects:
            schedule(after: Self.reconnectDelay) { driver in
                driver.isDisconnected = false
                // Like the backend on a new socket: the call's status, nothing else.
                driver.deliver(.status(.inCall))
            }
        case .staysDown:
            schedule(after: Self.reconnectDelay) { $0.onReconnectStopped?(.attemptsUsedUp) }
        }
    }

    // MARK: Delegated script (D9)

    /// Disclosure, the agent's opening from the brief, then the receptionist offers a slot.
    /// Attended: the agent pauses and asks the user; unattended: it promises a callback.
    private func playDelegated(_ setup: CallSetup, _ delegation: Delegation) {
        let opening = DelegatedDemo.opening(
            name: setup.details.name, goal: delegation.brief.goal,
            when: delegation.brief.constraints.first { $0.hasPrefix("preferred time: ") }
                .map { String($0.dropFirst("preferred time: ".count)) })
        schedule(after: 1) { $0.deliver(.status(.ringing)) }
        schedule(after: 2.5) { driver in
            driver.deliver(.status(.inCall))
            driver.say(.agent, DemoScript.disclosure)
        }
        schedule(after: 4.5) { $0.say(.agent, opening) }
        schedule(after: 7) { driver in
            driver.say(.receptionist, DelegatedDemo.offer)
            guard delegation.attended else {
                driver.say(.agent, DelegatedDemo.callbackLine)
                driver.schedule(after: 2) { $0.hangUp() }
                return
            }
            driver.say(.agent, DelegatedDemo.pauseLine)
            driver.openAskID = "demo-ask"
            driver.deliver(.ask(
                askID: "demo-ask", question: DelegatedDemo.offer, options: DelegatedDemo.options,
                fallback: DelegatedDemo.callbackLine, timeoutS: DelegatedDemo.askTimeout))
            driver.startAskTimer()
            if let drop = driver.options.connectionDrop {
                driver.schedule(after: Self.dropDelay) { $0.loseConnection(drop) }
            }
        }
    }

    private func answer(askID: String, choice: AskChoice) {
        guard askID == openAskID, let spoken = DelegatedDemo.options.first(where: { $0.choice == choice })?.spoken else {
            deliver(.error(code: "unknown_ask", message: "That question is no longer open."))
            return
        }
        askTimer?.cancel()
        guard choice != .wait else {
            // Like the backend: the agent holds the line and the question stays open.
            say(.agent, spoken)
            startAskTimer()
            return
        }
        resolveAsk(spoken: spoken, source: "user")
        let reply = choice == .yes ? DelegatedDemo.confirmation : DelegatedDemo.declined
        schedule(after: 2) { driver in
            driver.say(.receptionist, reply)
            driver.schedule(after: 1.5) { driver in
                driver.say(.agent, DelegatedDemo.closeLine)
                driver.hangUp()
            }
        }
    }

    private func startAskTimer() {
        askTimer = schedule(after: DelegatedDemo.askTimeout) { driver in
            driver.resolveAsk(spoken: DelegatedDemo.callbackLine, source: "timeout")
            driver.schedule(after: 2) { $0.hangUp() }
        }
    }

    private func resolveAsk(spoken: String, source: String) {
        guard let askID = openAskID else { return }
        openAskID = nil
        answers.append(spoken)
        transcript.append(TranscriptEntry(speaker: .agent, text: spoken, at: Date().timeIntervalSince1970))
        deliver(.askResolved(askID: askID, spoken: spoken, source: source))
    }

    private func say(_ speaker: CaptionSpeaker, _ text: String) {
        guard !isOver else { return }
        let at = Date().timeIntervalSince1970
        transcript.append(TranscriptEntry(speaker: speaker, text: text, at: at))
        deliver(.caption(text: text, at: at, speaker: speaker))
    }

    private func hangUp() {
        deliver(.status(.ended))
        finish()
    }

    private func deliver(_ message: ServerMessage) {
        guard !isOver, !isDisconnected else { return }
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
