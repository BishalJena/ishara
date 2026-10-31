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
        /// Delegated call (version B): the receptionist first asks "when?" with no time on
        /// offer, and offers a time once that is answered.
        var openTimeQuestion: OpenTimeQuestion?
        /// Seconds after a delegated call ends until its notes carry Bolna's own summary, as
        /// when its final `completed` webhook lands; nil leaves the summary out.
        var bolnaSummaryDelay: Double?
    }

    /// How the delegated call's open "when?" question is answered.
    struct OpenTimeQuestion: Sendable {
        /// Signed through the scripted recognizer a moment after the question, as the live
        /// script plays the user's signs; nil leaves the answer to a tap.
        var signedAnswer: Sign?
        /// The receptionist's words, as the live transcriber would hand them over.
        var question = DelegatedDemo.openQuestion
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
    /// Counts chips messages; a draft goes out only if no newer chips came in meanwhile.
    private var chipsRevision = 0
    private var failedStages: Set<Int> = []
    private var speakingTurn: TurnID?
    private var speakingTask: Task<Void, Never>?
    private var tasks: [Task<Void, Never>] = []
    private var isOver = false
    private var endedAt: Date?
    /// The simulated connection is down: nothing the app sends arrives.
    private var isDisconnected = false

    // Delegated call (D9), played from `DelegatedDemo`.
    private var setup: CallSetup?
    private var transcript: [TranscriptEntry] = []
    private var answers: [String] = []
    private var openAskID: String?
    private var openOptions: [AskOption] = []
    private var hasAsked = false
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
            if delegation.mode == .steer { playSteer(setup, delegation) } else { playDelegated(setup, delegation) }
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
        var notes = DelegatedDemo.notes(
            goal: delegation.brief.goal, name: setup.details.name, brief: delegation.brief.text,
            transcript: transcript, answers: answers, ready: isOver)
        if delegation.mode == .steer {
            notes.mode = .steer
            notes.steppedIn = steerSteppedIn
            notes.followUps = steerFollowUps
            if isOver {
                notes.outcome = steerBooked ? "booked" : "unclear"
                notes.summary += steerSaid.map { "You said: \"\($0)\"" }
                if steerBooked { notes.summary.append("They confirmed: \"You're booked for 10:30 tomorrow. Please bring an ID.\"") }
            }
        }
        if let delay = options.bolnaSummaryDelay, let endedAt,
           Date().timeIntervalSince(endedAt) >= delay * options.timeScale {
            notes.bolnaSummary = DelegatedDemo.automaticSummary(goal: delegation.brief.goal, name: setup.details.name)
        }
        return notes
    }

    // MARK: OutgoingMessageSink (what the backend would receive)

    func send(_ message: AppMessage) {
        guard !isOver, !isDisconnected else { return }
        switch message {
        case let .chips(turnID, signs):
            chipsRevision += 1
            let revision = chipsRevision
            let draft = DemoScript.draft(for: signs)
            schedule(after: 0.5) { driver in
                // Like the backend's draft_is_current: never a draft for chips that have since
                // changed. Drafts due at almost the same moment can arrive in either order.
                guard driver.chipsRevision == revision else { return }
                driver.deliver(.draft(turnID: turnID, text: draft.text, source: draft.source))
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
        case let .presence(present):
            isPresent = present
            if !present, let pending = pendingProposal, pending.origin == .agent { settleProposal(spoken: true) }
        case let .hold(turnID, composing):
            hold(turnID: turnID, composing: composing)
        case let .say(text):
            sayTyped(text)
        }
    }

    // MARK: Steer script

    private struct PendingProposal {
        let turnID: TurnID
        let text: String
        let origin: ProposalOrigin
        let then: () -> Void
    }

    private var isPresent = false
    private var isComposing = false
    private var heldLine: (() -> Void)?
    private var pendingProposal: PendingProposal?
    private var proposalTask: Task<Void, Never>?
    private var fillerIndex = 0
    private var steerStep = 0
    private var steerSteppedIn = 0
    private var steerFollowUps: [String] = []
    private var steerSaid: [String] = []
    private var steerBooked = false
    private static let fillers = ["One moment, please.", "Just a second, let me check.", "Bear with me a moment."]

    /// Disclosure and opening, then a receptionist who offers the wrong time first, then a
    /// fitting one, then confirms. Each agent line is proposed while the app is in front.
    private func playSteer(_ setup: CallSetup, _ delegation: Delegation) {
        let when = delegation.brief.constraints.first { $0.hasPrefix("preferred time: ") }
            .map { String($0.dropFirst("preferred time: ".count)) }
        let opening = DelegatedDemo.opening(name: setup.details.name, goal: delegation.brief.goal, when: when)
        schedule(after: 1) { $0.deliver(.status(.ringing)) }
        schedule(after: 2.5) { driver in
            driver.deliver(.status(.inCall))
            driver.say(.agent, DemoScript.disclosure)
        }
        schedule(after: 4.5) { driver in
            driver.say(.agent, opening)
            driver.schedule(after: 2.5) { $0.steerNext() }
        }
    }

    /// The receptionist's next turn and the agent's rule-bound answer to it.
    private func steerNext() {
        guard !isOver else { return }
        let step = steerStep
        steerStep += 1
        switch step {
        case 0:
            say(.receptionist, "We have 4 pm tomorrow. Does that work?")
            agentLine("No, 4 pm tomorrow doesn't work, sorry. Is there anything in the morning?") { $0.steerNext() }
        case 1:
            say(.receptionist, "Let me see. We have 10:30 tomorrow morning.")
            agentLine("Yes, 10:30 tomorrow morning works. Thank you.") { $0.steerNext() }
        case 2:
            say(.receptionist, "Can I get the date of birth?")
            steerFollowUps.append("Can I get the date of birth?")
            deliver(.followUp(text: "Can I get the date of birth?"))
            agentLine("I don't have that with me. Could I send it to you afterwards?") { $0.steerNext() }
        default:
            say(.receptionist, "That's fine. You're booked for 10:30 tomorrow. Please bring an ID.")
            steerBooked = true
            agentLine(DelegatedDemo.closeLine) { $0.hangUp() }
        }
    }

    /// Proposes `text` to a present user (spoken when the window runs out) or says it at once.
    private func agentLine(_ text: String, then: @escaping (FakeCallDriver) -> Void) {
        let continuation = { [weak self] in
            guard let self else { return }
            self.schedule(after: 2) { then($0) }
        }
        guard isPresent, !isComposing else {
            schedule(after: 1.5) { driver in
                driver.say(.agent, text)
                continuation()
            }
            return
        }
        schedule(after: 1.5) { $0.propose(text, origin: .agent, then: continuation) }
    }

    private func propose(_ text: String, origin: ProposalOrigin, then: @escaping () -> Void) {
        let turnID = TurnID("steer-\(UUID().uuidString.prefix(8))")!
        // Like the backend: Ishara's line waits a fixed 2 s; the user's preview 1.5 s.
        let window = origin == .agent ? 2.0 : 1.5
        pendingProposal = PendingProposal(turnID: turnID, text: text, origin: origin, then: then)
        deliver(.proposal(turnID: turnID, text: text, windowS: window, origin: origin))
        proposalTask = schedule(after: window) { $0.settleProposal(spoken: true) }
    }

    private func settleProposal(spoken: Bool) {
        guard let pending = pendingProposal else { return }
        proposalTask?.cancel()
        proposalTask = nil
        pendingProposal = nil
        deliver(.proposalResolved(turnID: pending.turnID, outcome: spoken ? .spoken : .held))
        guard spoken else { return }
        if pending.origin == .agent { say(.agent, pending.text) } else { note(pending.text) }
        pending.then()
    }

    private func hold(turnID: TurnID, composing: Bool) {
        if composing {
            isComposing = true
            if let pending = pendingProposal, pending.turnID == turnID {
                if pending.origin == .agent { heldLine = { [weak self] in self?.say(.agent, pending.text); pending.then() } }
                settleProposal(spoken: false)
            }
            // The agent covers the pause with a rotating filler.
            let filler = Self.fillers[fillerIndex % Self.fillers.count]
            fillerIndex += 1
            schedule(after: 1) { $0.say(.agent, filler) }
            return
        }
        isComposing = false
        if let held = heldLine {
            heldLine = nil
            schedule(after: 0.5) { _ in held() }
        }
    }

    private func sayTyped(_ text: String) {
        isComposing = false
        heldLine = nil
        steerSteppedIn += 1
        // As the backend's tidy() does without an LLM: a capital, and "?" for a question.
        let tidy = text.trimmingCharacters(in: .whitespacesAndNewlines)
        let questionWords: Set<String> = ["can", "could", "would", "will", "is", "are", "do", "does", "what", "when", "where", "how", "why", "any"]
        let isQuestion = questionWords.contains(tidy.split(separator: " ").first.map { $0.lowercased() } ?? "")
        let ending = tidy.hasSuffix(".") || tidy.hasSuffix("?") ? "" : (isQuestion ? "?" : ".")
        let polished = tidy.prefix(1).uppercased() + tidy.dropFirst() + ending
        let continuation: () -> Void = { [weak self] in
            self?.schedule(after: 2) { driver in
                driver.say(.receptionist, "Of course. Let me check that for you.")
                driver.schedule(after: 2) { $0.steerNext() }
            }
        }
        if isPresent {
            propose(polished, origin: .user, then: continuation)
        } else {
            note(polished)
            continuation()
        }
    }

    /// A user's typed line, spoken by the voice: in the notes' transcript, shown by the
    /// store itself (the app captions it as the user's when its preview ends).
    private func note(_ text: String) {
        steerSaid.append(text)
        transcript.append(TranscriptEntry(speaker: .agent, text: text, at: Date().timeIntervalSince1970))
    }

    func discardPending() {}

    // MARK: Script

    private func approve(turnID: TurnID, text: String) {
        // "Send now" on a proposed steer line: its window ends early.
        if pendingProposal?.turnID == turnID {
            settleProposal(spoken: true)
            return
        }
        if setup?.isSteer == true {
            // A signed line on a steer call: the user stepped in; the agent's line is dropped.
            if pendingProposal != nil { settleProposal(spoken: false) }
            isComposing = false
            heldLine = nil
            steerSteppedIn += 1
        }
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

    /// Disclosure, the agent's opening from the brief, then the receptionist offers a slot
    /// (or first asks "when?", with `Options.openTimeQuestion`).
    private func playDelegated(_ setup: CallSetup, _ delegation: Delegation) {
        let when = delegation.brief.constraints.first { $0.hasPrefix("preferred time: ") }
            .map { String($0.dropFirst("preferred time: ".count)) }
        let opening = DelegatedDemo.opening(name: setup.details.name, goal: delegation.brief.goal, when: when)
        schedule(after: 1) { $0.deliver(.status(.ringing)) }
        schedule(after: 2.5) { driver in
            driver.deliver(.status(.inCall))
            driver.say(.agent, DemoScript.disclosure)
        }
        schedule(after: 4.5) { $0.say(.agent, opening) }
        schedule(after: 7) { driver in
            if let question = driver.options.openTimeQuestion {
                driver.askWhen(delegation, when: when, question: question)
            } else {
                driver.offerSlot(delegation)
            }
        }
    }

    /// The receptionist offers a time. Attended: the agent pauses and asks the user yes /
    /// no / wait; unattended: it promises a callback.
    private func offerSlot(_ delegation: Delegation) {
        say(.receptionist, DelegatedDemo.offer)
        guard delegation.attended else {
            say(.agent, DelegatedDemo.callbackLine)
            schedule(after: 2) { $0.hangUp() }
            return
        }
        ask("demo-ask", question: DelegatedDemo.offer, options: DelegatedDemo.options)
    }

    /// The receptionist asks "when?" with no time on offer. Attended: the user picks a time
    /// word. Unattended: the agent says the brief's time, or promises a callback without one.
    private func askWhen(_ delegation: Delegation, when: String?, question: OpenTimeQuestion) {
        say(.receptionist, question.question)
        guard delegation.attended else {
            guard let when else {
                say(.agent, DelegatedDemo.callbackLine)
                schedule(after: 2) { $0.hangUp() }
                return
            }
            say(.agent, DelegatedDemo.timeLine(when))
            schedule(after: 2.5) { $0.offerSlot(delegation) }
            return
        }
        ask("demo-ask-when", question: question.question, options: DelegatedDemo.timeOptions)
        if let signedAnswer = question.signedAnswer, let recognition {
            schedule(after: 2.5) { _ in recognition.sign(.sign(signedAnswer)) }
        }
    }

    private func ask(_ askID: String, question: String, options askOptions: [AskOption]) {
        say(.agent, DelegatedDemo.pauseLine)
        openAskID = askID
        openOptions = askOptions
        deliver(.ask(
            askID: askID, question: question, options: askOptions,
            fallback: DelegatedDemo.callbackLine, timeoutS: DelegatedDemo.askTimeout))
        startAskTimer()
        // The connection drops once, after the call's first question.
        if !hasAsked, let drop = options.connectionDrop {
            schedule(after: Self.dropDelay) { $0.loseConnection(drop) }
        }
        hasAsked = true
    }

    private func answer(askID: String, choice: AskChoice) {
        guard askID == openAskID else {
            deliver(.error(code: "unknown_ask", message: "That question is no longer open."))
            return
        }
        guard let spoken = openOptions.first(where: { $0.choice == choice })?.spoken else {
            deliver(.error(code: "bad_choice", message: "Not one of the options."))
            return
        }
        askTimer?.cancel()
        resolveOrHold(choice: choice, spoken: spoken)
    }

    private func resolveOrHold(choice: AskChoice, spoken: String) {
        switch choice {
        case .wait:
            // Like the backend: the agent holds the line and the question stays open.
            say(.agent, spoken)
            startAskTimer()
        case .tomorrow, .morning, .now:
            // A time word settles nothing: the receptionist then offers a time.
            resolveAsk(spoken: spoken, source: "user")
            guard let delegation = setup?.delegation else { return }
            schedule(after: 2) { $0.offerSlot(delegation) }
        case .yes, .no:
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
        if endedAt == nil { endedAt = Date() }
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
