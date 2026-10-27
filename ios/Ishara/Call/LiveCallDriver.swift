import CallSession
import Foundation

/// The real call: `POST /calls` on the Ishara backend, then one WebSocket per call, via
/// CallSession's `LiveCall`. The backend asks Bolna to dial (Path B).
///
/// When the socket drops, the store goes silent ("Nothing will be sent") and this driver
/// reconnects a few times, waiting longer each time. Nothing from before the drop is
/// resent; the store comes back when the backend reports the call status again. A close
/// the backend meant as a refusal (4401 / 4404 / 4409) is never reconnected.
@MainActor
final class LiveCallDriver: CallDriver {
    static let defaultReconnectDelays: [Duration] = [.seconds(1), .seconds(2), .seconds(4)]

    private let client: BackendClient
    private let reconnectDelays: [Duration]
    private let sleep: @Sendable (Duration) async throws -> Void
    private let makeTurnID: () -> TurnID
    private var call: LiveCall?
    /// Kept after `close()` so the notes of an ended call can still be fetched.
    private var lastCallID: String?
    private var reconnectsUsed = 0
    private var reconnecting: Task<Void, Never>?

    var onReconnectStopped: ((ReconnectStop) -> Void)?

    init(
        client: BackendClient,
        reconnectDelays: [Duration] = LiveCallDriver.defaultReconnectDelays,
        sleep: @escaping @Sendable (Duration) async throws -> Void = { try await Task.sleep(for: $0) },
        makeTurnID: @escaping () -> TurnID = TurnID.random
    ) {
        self.client = client
        self.reconnectDelays = reconnectDelays
        self.sleep = sleep
        self.makeTurnID = makeTurnID
    }

    convenience init(config: BackendConfig) {
        self.init(client: BackendClient(config: config))
    }

    func start(_ setup: CallSetup) async throws -> TurnStore {
        let call = try await LiveCall.start(client: client, request: setup.startRequest, makeTurnID: makeTurnID)
        call.onConnectionLost = { [weak self] in self?.connectionLost() }
        self.call = call
        lastCallID = call.callID
        return call.store
    }

    func createBrief(_ request: BriefRequest) async throws -> Brief {
        try await client.createBrief(request)
    }

    func notes() async throws -> CallNotes {
        guard let lastCallID else { throw CallDriverError.noCall }
        return try await client.notes(callID: lastCallID)
    }

    func close() {
        reconnecting?.cancel()
        reconnecting = nil
        call = nil
        let client = client
        Task { await client.disconnect() }
    }

    private func connectionLost() {
        guard reconnecting == nil, let call else { return }
        let sleep = sleep
        reconnecting = Task { [weak self] in
            let close = await call.lastClose
            guard !Task.isCancelled, let self else { return }
            if let close, !close.allowsReconnect {
                self.stopReconnecting(.refused(close))
                return
            }
            guard self.reconnectsUsed < self.reconnectDelays.count else {
                self.stopReconnecting(.attemptsUsedUp)
                return
            }
            let delay = self.reconnectDelays[self.reconnectsUsed]
            self.reconnectsUsed += 1
            try? await sleep(delay)
            guard !Task.isCancelled else { return }
            self.reconnecting = nil
            guard self.call === call, call.store.state == .error else { return }
            await call.connect()
        }
    }

    private func stopReconnecting(_ reason: ReconnectStop) {
        reconnecting = nil
        onReconnectStopped?(reason)
    }
}
