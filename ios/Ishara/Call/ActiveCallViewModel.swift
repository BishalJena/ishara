import CallSession
import Foundation
import Observation

/// What the Active call screens show, and the buttons they offer.
///
/// The SEND safety rules live in `TurnStore` (CallSession), the single source of truth
/// for a call; this class only maps the store and recognition onto the screens:
/// - recognised signs become chips, unsure ones [?] chips (the store never sends those);
/// - SEND approves the shown draft once, or re-offers a not-delivered reply on a new turn;
/// - STOP, Clear, quick replies and End go straight to the store.
@MainActor
@Observable
final class ActiveCallViewModel {
    enum Phase: Equatable {
        case connecting(CallState)
        case live
        /// The connection dropped; nothing will be sent. It may come back.
        case interrupted(String)
        /// The connection is gone and won't be reconnected; only End is left.
        case disconnected(String)
        case ended(EndReason)
    }

    enum EndReason: Equatable {
        case userEnded
        /// The user ended the call but the backend couldn't confirm the hang-up.
        case hangUpUnconfirmed
        case remoteEnded
        case failed(String)
    }

    enum Delivery: Equatable {
        case idle
        case speaking(text: String)
        case delivered
        /// Spoken although the user tapped STOP.
        case deliveredDespiteStop
        case notDelivered(text: String)
        /// The user stopped it before it was spoken.
        case stopped(text: String)
    }

    static let connectionLostTitle = "Connection lost"

    let setup: CallSetup
    let recognition: any RecognitionController
    private(set) var store: TurnStore?
    private(set) var cameraState: CameraState = .watching
    private(set) var startFailure: String?
    private(set) var reconnectStop: ReconnectStop?
    /// D8 pick-one: the latest grey-zone sign, offered as "Did you mean …?" until the user
    /// taps it, dismisses it, or the next sign replaces it. Never a chip by itself.
    private(set) var candidate: Sign?
    /// The last sign couldn't be read because a hand left the picture.
    private(set) var showsFramingHint = false
    private var userEnded = false
    /// This call's id in Recent calls.
    let recordID = UUID()
    private let placedAt = Date()

    @ObservationIgnored let driver: any CallDriver

    init(setup: CallSetup, driver: any CallDriver, recognition: any RecognitionController) {
        self.setup = setup
        self.driver = driver
        self.recognition = recognition
        driver.onReconnectStopped = { [weak self] reason in self?.reconnectStop = reason }
    }

    // MARK: Derived state

    var phase: Phase {
        if let startFailure { return .ended(.failed(startFailure)) }
        guard let store else { return userEnded ? .ended(.userEnded) : .connecting(.dialing) }
        switch store.state {
        case .dialing, .ringing: return .connecting(store.state)
        case .inCall, .speaking: return .live
        case .error:
            if let reconnectStop { return .disconnected(Self.describe(reconnectStop)) }
            return .interrupted(store.notice ?? TurnStore.disconnectedNotice)
        case .ended:
            guard userEnded else { return .ended(.remoteEnded) }
            return .ended(store.lastError?.code == ServerError.endFailed ? .hangUpUnconfirmed : .userEnded)
        }
    }

    var isEnded: Bool {
        if case .ended = phase { true } else { false }
    }

    /// The call is over for good (ended, or the connection won't come back); the
    /// captions are what's left of it.
    var isCallOver: Bool {
        switch phase {
        case .ended, .disconnected: true
        case .connecting, .live, .interrupted: false
        }
    }

    /// D9: the agent pursues an approved brief; the user only answers its questions.
    var isDelegated: Bool { setup.delegation != nil }
    /// D9 attended: the user watches and answers the agent's questions by sign or tap
    /// (yes / no / wait, or a time word for an open "when?").
    var isAttended: Bool { setup.delegation?.attended ?? false }
    /// Signs matter on a live call, and on an attended delegated call (to answer questions).
    var watchesSigns: Bool { !isDelegated || isAttended }

    /// What Recent calls keeps once the call is over: its captions (the notes come later).
    /// Nil while it's on, or if it was never placed.
    var record: CallRecord? {
        guard isCallOver, store != nil else { return nil }
        return CallRecord(
            id: recordID, date: placedAt, contactName: setup.contact.name, mode: isDelegated ? .delegated : .live,
            captions: captions.map(CallRecord.Line.init), notes: nil)
    }

    var connectedAt: Date? { store?.connectedAt }
    var captions: [Caption] { store?.captions ?? [] }
    var chips: [Chip] { store?.chips ?? [] }
    var isStopRequested: Bool { store?.isStopRequested ?? false }

    var delivery: Delivery {
        switch store?.sending ?? .idle {
        case .idle: .idle
        case .speaking(_, let text): .speaking(text: text)
        case .delivered: .delivered
        case .deliveredDespiteStop: .deliveredDespiteStop
        case .notDelivered(let text): .notDelivered(text: text)
        case .stopped(let text): .stopped(text: text)
        }
    }

    var isSpeaking: Bool {
        if case .speaking = delivery { true } else { false }
    }

    /// STOP was refused: the reply was already being spoken.
    var isStopTooLate: Bool { store?.stopProgress == .tooLate }

    /// A short message for the latest backend error while the call is on. A too-late STOP
    /// and a failed hang-up have their own places on screen, so they aren't repeated here.
    var errorMessage: String? {
        guard !isEnded, let error = store?.lastError else { return nil }
        return Self.describe(error)
    }

    /// The unspoken sentence (not delivered, or stopped) SEND would offer again: only
    /// while the user hasn't started a new reply, so SEND never resends old text over new chips.
    var retryText: String? {
        guard let store, store.canResend, store.chips.isEmpty, store.draft == nil else { return nil }
        return store.unspokenText
    }

    var draft: DraftDisplay? {
        if let draft = store?.draft { return DraftDisplay(text: draft.text, badge: DraftBadge(draft.origin)) }
        guard let retryText else { return nil }
        if case .stopped = delivery { return DraftDisplay(text: retryText, badge: .stopped) }
        return DraftDisplay(text: retryText, badge: .notDelivered)
    }

    /// Recognised chips are on screen and their draft is still being written.
    var isComposing: Bool {
        guard let store else { return false }
        return !store.recognisedSigns.isEmpty && store.draft == nil
    }

    var canSend: Bool {
        guard let store else { return false }
        return store.canSend || retryText != nil
    }

    /// The delivery result shows until the user starts the next reply.
    var showsDeliveryResult: Bool { chips.isEmpty && store?.draft == nil }

    var canUseQuickReplies: Bool { phase == .live && !isSpeaking }

    // MARK: Lifecycle

    /// Places the call, then turns recognition results into chips until the screen goes
    /// away (the calling task is cancelled).
    func run() async {
        // Subscribe before placing the call so no recognition event falls in between.
        let events = recognition.signingEvents()
        await withDiscardingTaskGroup { group in
            group.addTask {
                for await event in events { await self.handle(event) }
            }
            await self.start()
        }
    }

    func start() async {
        guard store == nil, startFailure == nil else { return }
        do {
            attach(try await driver.start(setup))
        } catch {
            if !userEnded { startFailure = Self.describe(error) }
        }
    }

    /// Shows this store's call. If the user already tapped End while it was being placed,
    /// the call is ended straight away.
    func attach(_ store: TurnStore) {
        self.store = store
        if userEnded { store.end() }
    }

    func handle(_ event: RecognitionEvent) {
        guard !isEnded else { return }
        guard case .result(let result) = event else {
            if case .camera(let state) = event { cameraState = state }
            return
        }
        guard watchesSigns else { return }
        candidate = nil
        showsFramingHint = false
        switch result {
        case .sign(let sign):
            accept(sign)
        case .candidate(let sign):
            candidate = sign
        case .unsure:
            addUnsure()
        case .handLeftFrame:
            showsFramingHint = true
            addUnsure()
        }
    }

    /// The user tapped "Did you mean …?": the candidate counts as signed.
    func acceptCandidate() {
        guard let sign = candidate, !isEnded else { return }
        candidate = nil
        accept(sign)
    }

    func dismissCandidate() {
        candidate = nil
    }

    private func accept(_ sign: Sign) {
        // D9: while the agent waits for an answer, a signed option word answers it.
        if store?.answerIfAsked(sign) == true { return }
        // On a delegated call nothing is composed; only answers reach the call.
        guard !isDelegated else { return }
        store?.add(.recognised(sign))
    }

    private func addUnsure() {
        guard !isDelegated else { return }
        store?.add(.unsure())
    }

    /// Called when the user leaves the screen. Nothing is sent.
    func leave() {
        driver.close()
        recognition.stop()
    }

    // MARK: User actions

    func removeChip(_ chip: Chip) { store?.remove(chip) }

    /// The agent's open question on an attended delegated call (D9), if any.
    var openQuestion: OpenQuestion? { store?.openQuestion }

    func answer(_ choice: AskChoice) { store?.answer(choice) }

    func clear() { store?.clear() }

    func choose(_ reply: QuickReply) {
        guard canUseQuickReplies else { return }
        store?.useQuickReply(reply)
    }

    func send() {
        guard let store else { return }
        if store.canSend {
            store.send()
        } else if retryText != nil {
            store.resend()
        }
    }

    func stop() { store?.stop() }

    func end() {
        guard !isEnded else { return }
        userEnded = true
        store?.end()
        cameraState = .watching
        candidate = nil
    }

    // MARK: Private

    private static func describe(_ error: Error) -> String {
        switch error as? BackendError {
        case .httpStatus(401)?: "The app token was refused. Check the app configuration."
        case .httpStatus(403)?: "This contact isn't on the backend's allowed list."
        case .httpStatus(let code)?: "The backend couldn't start the call (HTTP \(code))."
        case .notHTTPResponse?: "The backend couldn't be reached."
        case nil: "The call couldn't start: \(error.localizedDescription)"
        }
    }

    private static func describe(_ error: ServerError) -> String? {
        switch error.code {
        case ServerError.cannotInterrupt, ServerError.endFailed: nil
        case "stale_turn": "That reply was out of date, so it wasn't sent."
        case "already_approved": "That reply was already sent."
        case "busy_speaking": "Wait until the current reply has been spoken."
        case "call_not_live": "The call isn't connected yet. Nothing was sent."
        case "call_ended": "The call has ended. Nothing will be sent."
        case "bad_message": "The backend didn't understand the app. Nothing was sent."
        default: "Something went wrong on the backend."
        }
    }

    private static func describe(_ stop: ReconnectStop) -> String {
        switch stop {
        case .refused(.unauthorized): "The backend refused the app token"
        case .refused(.unknownCall): "The backend no longer knows this call"
        case .refused(.replaced): "This call is now connected somewhere else"
        case .refused(.dropped), .attemptsUsedUp: "The connection couldn't be restored"
        }
    }
}
