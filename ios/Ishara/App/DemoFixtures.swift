#if DEBUG
import CallSession
import Foundation

/// Swallows outgoing messages so a fixture's state stays put.
@MainActor
private final class SilentSink: OutgoingMessageSink {
    func send(_ message: AppMessage) {}
    func discardPending() {}
}

/// Hands the view model a store that was prepared in advance.
@MainActor
final class FixtureCallDriver: CallDriver {
    let store = TurnStore(sink: SilentSink(), initialState: .dialing)

    func start(_ setup: CallSetup) async throws -> TurnStore { store }
    func close() {}
}

extension DemoFixture {
    /// Builds the call screen state by replaying PLAN §1 messages into a real TurnStore.
    @MainActor
    func makeActiveCall() -> ActiveCallViewModel? {
        guard self != .home, self != .getReady else { return nil }
        let driver = FixtureCallDriver()
        let store = driver.store
        let model = ActiveCallViewModel(setup: .demo, driver: driver, recognition: ScriptedRecognitionController())
        model.attach(store)

        store.receive(.status(.inCall))
        store.add(.recognised(.hello))
        store.receive(.draft(turnID: store.currentTurnID, text: "Hello, I'd like a doctor's appointment tomorrow.", source: .llm))
        let firstTurn = store.currentTurnID
        store.send()
        store.receive(.spoken(turnID: firstTurn))
        store.receive(.caption(text: "We have 4 pm tomorrow. Does that work?", at: Date().timeIntervalSince1970))

        [Sign.no, .afternoon, .morning].forEach { store.add(.recognised($0)) }
        store.add(.unsure())
        store.receive(.draft(turnID: store.currentTurnID, text: "No. In the afternoon, please. In the morning, please.", source: .template))
        model.handle(.camera(.signing))
        if self == .signing { return model }

        if let wrong = store.chips.first(where: { $0.sign == .afternoon }) {
            store.remove(wrong)
        }
        store.receive(.draft(turnID: store.currentTurnID, text: "No, sorry, 4 pm doesn't work. Is there anything tomorrow morning?", source: .llm))
        model.handle(.camera(.watching))
        let secondTurn = store.currentTurnID
        store.send()

        switch self {
        case .delivered:
            store.receive(.spoken(turnID: secondTurn))
        case .notDelivered:
            store.receive(.notDelivered(turnID: secondTurn, reason: "no_confirmation"))
        case .ended:
            model.end()
        case .connectionLost:
            store.connectionLost()
        default:
            break
        }
        return model
    }
}
#endif
