import Foundation
import Observation

/// One chip on the signing screen. Only recognised chips are ever sent; unsure `?` chips
/// are shown so the user knows to sign again.
public struct Chip: Identifiable, Equatable, Sendable {
    public enum Kind: Equatable, Sendable {
        case recognised(Sign)
        case unsure
    }

    public let id: UUID
    public let kind: Kind

    public init(id: UUID = UUID(), kind: Kind) {
        self.id = id
        self.kind = kind
    }

    public static func recognised(_ sign: Sign) -> Chip { Chip(kind: .recognised(sign)) }
    public static func unsure() -> Chip { Chip(kind: .unsure) }

    /// The recognised sign, or nil for an unsure chip, which is never sent.
    public var sign: Sign? {
        if case let .recognised(sign) = kind { return sign }
        return nil
    }
}

/// One line of the call transcript: the receptionist's words, a fixed line the call agent
/// said without a SEND, or a reply of the user's that the backend confirmed as spoken.
public struct Caption: Equatable, Sendable {
    public enum Speaker: Equatable, Sendable {
        case receptionist
        /// The call agent's own fixed lines (disclosure, holding line, goodbye).
        case agent
        case user
    }

    public let text: String
    public let at: Date
    public let speaker: Speaker

    public init(text: String, at: Date, speaker: Speaker = .receptionist) {
        self.text = text
        self.at = at
        self.speaker = speaker
    }
}

/// The sentence SEND would speak.
public struct Draft: Equatable, Sendable {
    public enum Origin: Equatable, Sendable {
        case llm
        case template
        case quickReply
    }

    public let text: String
    public let origin: Origin
}

/// Full polite sentences for questions no sign covers. SEND is still required.
public enum QuickReply: CaseIterable, Sendable {
    case yes
    case no
    case wait
    case `repeat`

    public var text: String {
        switch self {
        case .yes: "Yes."
        case .no: "No."
        case .wait: "Please wait a moment, I'm signing my reply."
        case .repeat: "Sorry, could you please repeat that?"
        }
    }
}

/// What happened to the last approved sentence.
public enum SendingPhase: Equatable, Sendable {
    case idle
    case speaking(turnID: TurnID, text: String)
    case delivered
    /// No confirmation arrived; the user may re-SEND `text`. Never resent automatically.
    case notDelivered(text: String)
}

public struct ServerError: Equatable, Sendable {
    public let code: String
    public let message: String
}

/// The single source of truth for one call on the app side.
///
/// Safety rules (PLAN.md §4, docs/WORKFLOW.md): nothing is spoken unless the user taps SEND,
/// an approval is used once and tied to its turn, unsure chips and stale drafts never reach
/// the call, and after End or a disconnect nothing is sent on the user's behalf.
@MainActor
@Observable
public final class TurnStore {
    public static let disconnectedNotice = "Nothing will be sent"

    public private(set) var state: CallState
    /// When the call first reached `in_call` or `speaking`; drives the call timer.
    public private(set) var connectedAt: Date?
    public private(set) var captions: [Caption] = []
    public private(set) var currentTurnID: TurnID
    public private(set) var chips: [Chip] = []
    public private(set) var draft: Draft?
    public private(set) var sending: SendingPhase = .idle
    /// STOP was sent for the reply being spoken; it isn't sent twice.
    public private(set) var isStopRequested = false
    /// Shown to the user when the call can no longer carry messages.
    public private(set) var notice: String?
    public private(set) var lastError: ServerError?

    private let sink: any OutgoingMessageSink
    private let makeTurnID: () -> TurnID

    public init(
        sink: any OutgoingMessageSink,
        initialState: CallState = .dialing,
        makeTurnID: @escaping () -> TurnID = TurnID.random
    ) {
        self.sink = sink
        self.state = initialState
        self.makeTurnID = makeTurnID
        self.currentTurnID = makeTurnID()
        if isLive { connectedAt = Date() }
    }

    /// The signs a `chips` message would carry, in order.
    public var recognisedSigns: [Sign] { chips.compactMap(\.sign) }

    /// True when SEND would approve the shown draft. Not while an approved reply is still
    /// being spoken: SEND becomes STOP until it is confirmed or reported not delivered.
    public var canSend: Bool {
        guard isLive, !isAwaitingDelivery, let draft else { return false }
        return Self.isSendable(draft.text)
    }

    /// True when `resend()` would approve the not-delivered text again.
    public var canResend: Bool {
        guard isLive, case .notDelivered = sending else { return false }
        return true
    }

    // MARK: User actions

    /// Adds a chip. Returns false when the call is over or a recognised chip would exceed
    /// the backend's limit of `ProtocolLimits.maxChips`.
    @discardableResult
    public func add(_ chip: Chip) -> Bool {
        guard acceptsInput else { return false }
        if chip.sign != nil, recognisedSigns.count >= ProtocolLimits.maxChips { return false }
        chips.append(chip)
        if chip.sign != nil { recognisedChipsChanged() }
        return true
    }

    public func remove(_ chip: Chip) {
        guard acceptsInput, let index = chips.firstIndex(where: { $0.id == chip.id }) else { return }
        let removed = chips.remove(at: index)
        if removed.sign != nil { recognisedChipsChanged() }
    }

    /// Puts a quick-reply sentence in the draft on a fresh turn. Nothing is sent until SEND.
    public func useQuickReply(_ reply: QuickReply) {
        guard acceptsInput else { return }
        beginNewTurn()
        draft = Draft(text: reply.text, origin: .quickReply)
    }

    /// Removes every chip and the draft. A new turn begins, so a late draft for the old
    /// chips is stale; nothing is sent.
    public func clear() {
        guard !chips.isEmpty || draft != nil else { return }
        beginNewTurn()
    }

    /// Approves exactly the shown draft, once. A new turn then begins with no chips or draft.
    public func send() {
        guard canSend, let draft else { return }
        approve(draft.text, turnID: currentTurnID)
    }

    /// After "not delivered", approves the same text again on a new turn id.
    public func resend() {
        guard canResend, case let .notDelivered(text) = sending else { return }
        approve(text, turnID: makeTurnID())
    }

    /// Asks the backend to cancel the reply being spoken, once per reply.
    public func stop() {
        guard acceptsInput, isAwaitingDelivery, !isStopRequested else { return }
        isStopRequested = true
        sink.send(.stop)
    }

    /// Ends the call. Anything still queued is dropped first so nothing speaks after End.
    public func end() {
        guard state != .ended else { return }
        sink.discardPending()
        sink.send(.end)
        finish()
    }

    // MARK: Backend events

    public func receive(_ message: ServerMessage) {
        guard state != .ended else { return }
        switch message {
        case .status(.ended):
            sink.discardPending()
            finish()
        case .status(.error):
            goSilent()
        case let .status(newState):
            state = newState
            notice = nil
            if isLive, connectedAt == nil { connectedAt = Date() }
        case let .caption(text, at, speaker):
            captions.append(Caption(
                text: text, at: Date(timeIntervalSince1970: at),
                speaker: speaker == .agent ? .agent : .receptionist))
        case let .draft(turnID, text, source):
            // A draft for an older turn, or for chips the user has since removed, is stale.
            guard turnID == currentTurnID, !recognisedSigns.isEmpty else { return }
            draft = Draft(text: text, origin: source == .llm ? .llm : .template)
        case let .spoken(turnID):
            if case let .speaking(speakingTurn, text) = sending, speakingTurn == turnID {
                captions.append(Caption(text: text, at: Date(), speaker: .user))
                settle(.delivered)
            }
        case let .notDelivered(turnID, _):
            if case let .speaking(speakingTurn, text) = sending, speakingTurn == turnID {
                settle(.notDelivered(text: text))
            }
        case let .error(code, message):
            lastError = ServerError(code: code, message: message)
        case .unknown:
            break
        }
    }

    /// The socket closed. Nothing pending is sent, drafts are wiped and nothing is resent
    /// when a new connection arrives.
    public func connectionLost() {
        guard state != .ended else { return }
        goSilent()
    }

    /// Applies every event, then treats the end of the stream as a lost connection. If the
    /// calling task is cancelled (the app is replacing the connection on purpose), it stops
    /// without reporting a disconnect.
    public func consume(_ events: AsyncStream<ServerMessage>) async {
        for await message in events {
            guard !Task.isCancelled else { return }
            receive(message)
        }
        guard !Task.isCancelled else { return }
        connectionLost()
    }

    // MARK: Private

    private var acceptsInput: Bool { state != .ended && state != .error }
    private var isLive: Bool { state == .inCall || state == .speaking }

    private var isAwaitingDelivery: Bool {
        if case .speaking = sending { return true }
        return false
    }

    /// 1–300 Unicode scalars and not just whitespace, which would approve silence.
    private static func isSendable(_ text: String) -> Bool {
        (1...ProtocolLimits.maxSpokenCharacters).contains(text.unicodeScalars.count)
            && !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private func recognisedChipsChanged() {
        // The shown draft described the old chips; wait for the backend's new one.
        draft = nil
        let signs = recognisedSigns
        guard !signs.isEmpty else { return }
        sink.send(.chips(turnID: currentTurnID, chips: signs))
    }

    private func approve(_ text: String, turnID: TurnID) {
        sink.send(.approve(turnID: turnID, text: text))
        settle(.speaking(turnID: turnID, text: text))
        beginNewTurn()
    }

    private func settle(_ phase: SendingPhase) {
        sending = phase
        isStopRequested = false
    }

    private func beginNewTurn() {
        currentTurnID = makeTurnID()
        chips = []
        draft = nil
    }

    private func goSilent() {
        sink.discardPending()
        state = .error
        notice = Self.disconnectedNotice
        settle(.idle)
        beginNewTurn()
    }

    /// Captions stay as a read-only transcript of the call; everything that could still be
    /// sent (chips, draft, a pending approval) is wiped.
    private func finish() {
        state = .ended
        settle(.idle)
        notice = nil
        beginNewTurn()
    }
}
