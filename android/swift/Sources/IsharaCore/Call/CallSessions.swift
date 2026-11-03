import CallSession
import Foundation
import Observation

/// The call sessions Kotlin holds, by id. Each wraps one `TurnStore`; a snapshot event goes
/// out whenever any of its observable properties changes.
@MainActor
final class CallSessions {
    static let shared = CallSessions()

    private var sessions: [Int32: CallSessionBox] = [:]
    private var nextID: Int32 = 1

    func session(_ id: Int32) throws(BridgeError) -> CallSessionBox {
        guard let session = sessions[id] else { throw .unknownSession(id) }
        return session
    }

    /// A store whose outgoing messages go to Kotlin as `outgoing` events.
    func startLocal(initialState: CallState) -> CallSessionBox {
        let id = allocateID()
        let sink = BridgeSink(sessionID: id)
        let session = CallSessionBox(id: id, kind: .local, store: TurnStore(sink: sink, initialState: initialState))
        register(session)
        return session
    }

    /// Places the call (`POST /calls`), opens its socket and registers its store.
    func startLive(config: BackendConfig, request: StartCallRequest) async throws -> CallSessionBox {
        let client = BackendClient(config: config)
        let call = try await LiveCall.start(client: client, request: request)
        let id = allocateID()
        let session = CallSessionBox(id: id, kind: .live(call, client), store: call.store)
        call.onConnectionLost = { [weak session] in
            // Kotlin sees the silent store before it hears about the loss.
            session?.emitSnapshot()
            EventSink.emit(#"{"type":"connectionLost","sessionId":\#(id)}"#)
        }
        register(session)
        return session
    }

    func close(_ id: Int32) {
        guard let session = sessions.removeValue(forKey: id) else { return }
        session.close()
    }

    private func allocateID() -> Int32 {
        defer { nextID += 1 }
        return nextID
    }

    private func register(_ session: CallSessionBox) {
        sessions[session.id] = session
        session.observe()
    }
}

@MainActor
final class CallSessionBox {
    enum Kind {
        case local
        case live(LiveCall, BackendClient)
    }

    let id: Int32
    let kind: Kind
    let store: TurnStore
    private var isClosed = false

    init(id: Int32, kind: Kind, store: TurnStore) {
        self.id = id
        self.kind = kind
        self.store = store
    }

    var snapshot: CallSnapshot { CallSnapshot(store) }

    /// Emits the current snapshot on the next main-queue turn and again after every change,
    /// at most once per turn: `onChange` fires once per registration, and the snapshot is
    /// read (and tracking re-armed) only when the scheduled emission runs.
    func observe() {
        Task { @MainActor [weak self] in self?.emitAndTrack() }
    }

    private func emitAndTrack() {
        guard !isClosed else { return }
        let snapshot = withObservationTracking {
            CallSnapshot(store)
        } onChange: { [weak self] in
            Task { @MainActor in self?.emitAndTrack() }
        }
        emit(snapshot)
    }

    /// Emits the current snapshot right away, ahead of the scheduled one.
    func emitSnapshot() {
        guard !isClosed else { return }
        emit(snapshot)
    }

    private func emit(_ snapshot: CallSnapshot) {
        EventSink.emit(encodeJSON(StateEvent(sessionId: id, snapshot: snapshot)))
    }

    func close() {
        isClosed = true
        if case let .live(_, client) = kind {
            Task { await client.disconnect() }
        }
    }

    private struct StateEvent: Encodable {
        let type = "state"
        let sessionId: Int32
        let snapshot: CallSnapshot
    }
}

/// A local session's outgoing messages, as Kotlin events carrying the exact wire JSON.
@MainActor
final class BridgeSink: OutgoingMessageSink {
    private let sessionID: Int32

    init(sessionID: Int32) {
        self.sessionID = sessionID
    }

    func send(_ message: AppMessage) {
        // `AppMessage` always encodes; a failure is a programmer error.
        let wire = try! WireCoding.encodeText(message)
        EventSink.emit(#"{"type":"outgoing","sessionId":\#(sessionID),"message":\#(wire)}"#)
    }

    func discardPending() {
        EventSink.emit(#"{"type":"discardPending","sessionId":\#(sessionID)}"#)
    }
}
