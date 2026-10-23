import Foundation
import Observation

/// State and rules for the Active call screens.
///
/// Safety rules it enforces (PLAN §3 and §4):
/// - nothing is approved unless the user taps SEND;
/// - an approval is single use and tied to its turn; SEND wipes chips and draft;
/// - unsure chips, stale drafts, failed deliveries and ended calls never send anything.
@MainActor
@Observable
final class ActiveCallViewModel {
    enum Phase: Equatable {
        case connecting(CallStatus)
        case live
        case ended(EndReason)
    }

    enum EndReason: Equatable {
        case userEnded
        case remoteEnded
        case failed(String)
    }

    enum Delivery: Equatable {
        case idle
        case speaking(turnID: TurnID, draft: Draft)
        case delivered(text: String)
        case notDelivered(text: String)
    }

    let setup: CallSetup

    private(set) var phase: Phase = .connecting(.dialing)
    private(set) var connectedAt: Date?
    private(set) var captions: [CaptionEntry] = []
    private(set) var cameraState: CameraState = .watching
    private(set) var chips: [Chip] = []
    private(set) var draft: Draft?
    private(set) var delivery: Delivery = .idle
    private(set) var isStopRequested = false
    private(set) var currentTurnID: TurnID = 1

    /// False after a quick reply so a late composer draft can't overwrite the
    /// sentence the user picked. A chip change turns it back on.
    private var acceptsComposerDrafts = true

    private let driver: CallDriver

    init(setup: CallSetup, driver: CallDriver) {
        self.setup = setup
        self.driver = driver
    }

    // MARK: Derived state

    var isEnded: Bool {
        if case .ended = phase { true } else { false }
    }

    var isSpeaking: Bool {
        if case .speaking = delivery { true } else { false }
    }

    var canSend: Bool {
        guard phase == .live, !isSpeaking, let draft else { return false }
        return !draft.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    /// Chips can change while a reply is being spoken: the camera keeps
    /// watching so the user can sign the next thing.
    var canEditChips: Bool { !isEnded }

    var canUseQuickReplies: Bool { !isEnded && !isSpeaking }

    private var recognisedWords: [String] { chips.compactMap(\.word) }

    // MARK: Lifecycle

    /// Starts the call and handles events until the call's stream finishes or
    /// the calling task is cancelled (for example when the screen goes away).
    func run() async {
        driver.start(setup)
        for await event in driver.events {
            handle(event)
        }
    }

    func handle(_ event: CallEvent) {
        guard !isEnded else { return }
        switch event {
        case .status(let status):
            apply(status)
        case .caption(let text, let at):
            captions.append(CaptionEntry(speaker: .receptionist, text: text, at: at))
        case .draft(let turnID, let text, let source):
            acceptDraft(turnID: turnID, text: text, source: source)
        case .spoken(let turnID):
            confirmSpoken(turnID: turnID)
        case .notDelivered(let turnID):
            markNotDelivered(turnID: turnID)
        case .error(let message):
            endCall(.failed(message))
        case .recognition(let result):
            addChip(for: result)
        case .camera(let state):
            cameraState = state
        }
    }

    // MARK: User actions

    func removeChip(_ chip: Chip) {
        guard canEditChips, let index = chips.firstIndex(where: { $0.id == chip.id }) else { return }
        chips.remove(at: index)
        if chip.word != nil {
            requestRecompose()
        }
    }

    func clear() {
        guard canEditChips, !chips.isEmpty || draft != nil else { return }
        let hadWords = !recognisedWords.isEmpty
        chips.removeAll()
        draft = nil
        if hadWords {
            driver.updateChips(turnID: currentTurnID, words: [])
        }
    }

    func choose(_ reply: QuickReply) {
        guard canUseQuickReplies else { return }
        delivery = .idle
        acceptsComposerDrafts = false
        draft = Draft(text: reply.sentence, source: .quickReply)
    }

    func send() {
        guard canSend, let draft else { return }
        let turnID = currentTurnID
        driver.approve(turnID: turnID, text: draft.text)
        delivery = .speaking(turnID: turnID, draft: draft)
        isStopRequested = false
        chips.removeAll()
        self.draft = nil
        currentTurnID += 1
        acceptsComposerDrafts = true
    }

    func stop() {
        guard isSpeaking, !isStopRequested, !isEnded else { return }
        isStopRequested = true
        driver.stop()
    }

    func end() {
        guard !isEnded else { return }
        driver.end()
        endCall(.userEnded)
    }

    // MARK: Event handling

    private func apply(_ status: CallStatus) {
        switch status {
        case .dialing, .ringing:
            phase = .connecting(status)
        case .inCall, .speaking:
            if connectedAt == nil { connectedAt = .now }
            phase = .live
        case .ended:
            endCall(.remoteEnded)
        case .error:
            endCall(.failed("The call ran into a problem."))
        }
    }

    private func acceptDraft(turnID: TurnID, text: String, source: DraftSource) {
        guard turnID == currentTurnID, acceptsComposerDrafts, !recognisedWords.isEmpty else { return }
        draft = Draft(text: text, source: source)
    }

    private func confirmSpoken(turnID: TurnID) {
        guard case .speaking(let speakingTurn, let draft) = delivery, speakingTurn == turnID else { return }
        captions.append(CaptionEntry(speaker: .user, text: draft.text, at: .now))
        delivery = .delivered(text: draft.text)
        isStopRequested = false
    }

    /// Offers the same sentence again under the current turn. Never resends by itself.
    private func markNotDelivered(turnID: TurnID) {
        guard case .speaking(let speakingTurn, let failed) = delivery, speakingTurn == turnID else { return }
        delivery = .notDelivered(text: failed.text)
        isStopRequested = false
        if draft == nil {
            draft = failed
            acceptsComposerDrafts = false
        }
    }

    private func addChip(for result: RecognitionResult) {
        guard canEditChips else { return }
        if !isSpeaking { delivery = .idle }
        switch result {
        case .sign(let word):
            chips.append(Chip(kind: .recognised(word)))
            requestRecompose()
        case .unsure:
            chips.append(Chip(kind: .unsure))
        }
    }

    private func requestRecompose() {
        acceptsComposerDrafts = true
        let words = recognisedWords
        if words.isEmpty {
            draft = nil
        }
        driver.updateChips(turnID: currentTurnID, words: words)
    }

    private func endCall(_ reason: EndReason) {
        phase = .ended(reason)
        chips.removeAll()
        draft = nil
        delivery = .idle
        isStopRequested = false
        cameraState = .watching
    }
}
