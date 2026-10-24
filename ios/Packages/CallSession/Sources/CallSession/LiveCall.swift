import Foundation

/// Wires a `BackendClient` to a `TurnStore` for one call: starts it, feeds socket events
/// into the store and routes the store's messages through an ordered outbox.
@MainActor
public final class LiveCall {
    public let callID: String
    public let store: TurnStore

    private let client: BackendClient
    private var listener: Task<Void, Never>?

    /// Places the call (`POST /calls`) and opens its socket.
    public static func start(
        client: BackendClient,
        contactID: String,
        purpose: CallPurpose,
        makeTurnID: @escaping () -> TurnID = TurnID.random
    ) async throws -> LiveCall {
        let start = try await client.startCall(contactID: contactID, purpose: purpose)
        let call = LiveCall(client: client, start: start, makeTurnID: makeTurnID)
        await call.connect()
        return call
    }

    private init(client: BackendClient, start: CallStart, makeTurnID: @escaping () -> TurnID) {
        self.client = client
        self.callID = start.callID
        let outbox = MessageOutbox(sender: client)
        let store = TurnStore(sink: outbox, initialState: start.state, makeTurnID: makeTurnID)
        outbox.onFailure = { [weak store] _ in store?.connectionLost() }
        self.store = store
    }

    /// Why the socket last closed, so the UI can tell a drop from a refusal. Nil while open.
    public var lastClose: CallSocketClose? {
        get async { await client.lastClose }
    }

    /// Opens (or reopens, after a disconnect) the call socket. Nothing from before a
    /// disconnect is resent; the store stays in `.error` until the backend reports a status.
    /// Does nothing after a close that reconnecting can't fix (see `allowsReconnect`).
    public func connect() async {
        if let close = await client.lastClose, !close.allowsReconnect { return }
        listener?.cancel()
        await client.connect(callID: callID)
        let events = await client.events
        listener = Task { [store] in await store.consume(events) }
    }
}
