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
}
