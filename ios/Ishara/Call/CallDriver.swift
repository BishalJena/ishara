import CallSession
import Foundation

/// Places a call and hands back the `TurnStore` that holds its state and enforces the
/// SEND safety rules. Everything after that (chips, SEND, STOP, End and backend events)
/// goes through the store, so the real backend and the fake demo call share one set of
/// rules.
@MainActor
protocol CallDriver: AnyObject {
    /// Asks for the call (`POST /calls` on the real backend). Throws when it can't be
    /// placed, for example a bad app token, a contact not on the allowlist or no network.
    func start(_ setup: CallSetup) async throws -> TurnStore

    /// Lets go of the connection once the call screen goes away. Sends nothing.
    func close()

    /// Runs when the driver stops bringing a dropped call connection back, so the screen
    /// can stop promising a reconnect.
    var onReconnectStopped: ((ReconnectStop) -> Void)? { get set }
}

/// Why a driver stopped reconnecting a dropped call socket.
enum ReconnectStop: Equatable {
    /// The backend closed the socket with a code a reconnect can't fix: a refused app
    /// token (4401), a call it no longer knows (4404) or a newer socket that took over (4409).
    case refused(CallSocketClose)
    /// Every scheduled reconnect was tried.
    case attemptsUsedUp
}
