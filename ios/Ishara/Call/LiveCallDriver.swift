import CallSession
import Foundation
import OSLog

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

    private let log = Logger(subsystem: "ai.ishara.demo", category: "call")
    private let client: BackendClient
    private let reconnectDelays: [Duration]
    private let sleep: @Sendable (Duration) async throws -> Void
    private let makeTurnID: () -> TurnID
    private var call: LiveCall?
    /// Kept after `close()` so the notes of an ended call can still be fetched.
    private var lastCallID: String?
    private var lastBriefID: String?
    private var starting: Task<TurnStore, Error>?
    private var reconnectsUsed = 0
    private var reconnecting: Task<Void, Never>?

    var backendCallID: String? { lastCallID }
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
        if let starting { return try await starting.value }
        lastBriefID = setup.delegation?.brief.briefID
        // A view task can disappear after the server has dialled. Own startup here;
        // cancelling the screen must not cancel and forget an accepted call.
        let task = Task { @MainActor [self] in
            log.info("Starting call request")
            let accepted: CallStart
            do {
                accepted = try await client.startCall(setup.startRequest)
            } catch {
                guard let lastBriefID,
                      let recovered = try? await client.callForBrief(lastBriefID) else { throw error }
                log.notice("Recovered the accepted call after a lost startup response")
                accepted = recovered
            }
            let call = LiveCall(client: client, start: accepted, makeTurnID: makeTurnID)
            self.call = call
            lastCallID = call.callID  // retain identity before any live-feed setup
            log.info("Call identity retained; connecting live feed")
            call.onConnectionLost = { [weak self] in self?.connectionLost() }
            await call.connect()
            return call.store
        }
        starting = task
        return try await task.value
    }

    func createBrief(_ request: BriefRequest) async throws -> Brief {
        let brief = try await client.createBrief(request)
        lastBriefID = brief.briefID
        return brief
    }

    func notes() async throws -> CallNotes {
        if lastCallID == nil, let lastBriefID {
            lastCallID = try await client.callForBrief(lastBriefID).callID
        }
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
