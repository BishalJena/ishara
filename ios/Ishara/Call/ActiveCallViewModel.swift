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
        case remoteEnded
        case failed(String)
    }

    enum Delivery: Equatable {
        case idle
        case speaking(text: String)
        case delivered
        case notDelivered(text: String)
    }

    static let connectionLostTitle = "Connection lost"

    let setup: CallSetup
    let recognition: any RecognitionController
    private(set) var store: TurnStore?
    private(set) var cameraState: CameraState = .watching
    private(set) var startFailure: String?
    private(set) var reconnectStop: ReconnectStop?
    private var userEnded = false

    @ObservationIgnored private let driver: any CallDriver

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
        case .ended: return .ended(userEnded ? .userEnded : .remoteEnded)
        }
    }

    var isEnded: Bool {
        if case .ended = phase { true } else { false }
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
        case .notDelivered(let text): .notDelivered(text: text)
        }
    }

    var isSpeaking: Bool {
        if case .speaking = delivery { true } else { false }
    }

    /// The not-delivered sentence SEND would offer again: only while the user hasn't
    /// started a new reply, so SEND never resends old text over new chips.
    var retryText: String? {
        guard let store, store.canResend, store.chips.isEmpty, store.draft == nil,
              case .notDelivered(let text) = store.sending
        else { return nil }
        return text
    }

    var draft: DraftDisplay? {
        if let draft = store?.draft { return DraftDisplay(text: draft.text, badge: DraftBadge(draft.origin)) }
        return retryText.map { DraftDisplay(text: $0, badge: .notDelivered) }
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
        switch event {
        case .camera(let state):
            cameraState = state
        case .result(.sign(let sign)):
            store?.add(.recognised(sign))
        case .result(.unsure):
            store?.add(.unsure())
        }
    }

    /// Called when the user leaves the screen. Nothing is sent.
    func leave() {
        driver.close()
        recognition.stop()
    }

    // MARK: User actions

    func removeChip(_ chip: Chip) { store?.remove(chip) }

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

    private static func describe(_ stop: ReconnectStop) -> String {
        switch stop {
        case .refused(.unauthorized): "The backend refused the app token"
        case .refused(.unknownCall): "The backend no longer knows this call"
        case .refused(.replaced): "This call is now connected somewhere else"
        case .refused(.dropped), .attemptsUsedUp: "The connection couldn't be restored"
        }
    }
}
