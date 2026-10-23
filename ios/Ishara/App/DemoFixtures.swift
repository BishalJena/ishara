#if DEBUG
import Foundation

/// A driver that never emits anything, so a fixture's state stays put.
@MainActor
final class StillCallDriver: CallDriver {
    let events: AsyncStream<CallEvent>

    init() {
        events = AsyncStream { _ in }
    }

    func start(_ setup: CallSetup) {}
    func updateChips(turnID: TurnID, words: [String]) {}
    func approve(turnID: TurnID, text: String) {}
    func stop() {}
    func end() {}
}

extension DemoFixture {
    /// Builds the call screen state by replaying PLAN §1 events into a view model.
    @MainActor
    func makeActiveCall() -> ActiveCallViewModel? {
        guard self != .home, self != .getReady else { return nil }
        let model = ActiveCallViewModel(setup: .demo, driver: StillCallDriver())

        model.handle(.status(.inCall))
        model.handle(.recognition(.sign("hello")))
        model.handle(.draft(turnID: 1, text: "Hello, I'd like a doctor's appointment tomorrow.", source: .llm))
        model.send()
        model.handle(.spoken(turnID: 1))
        model.handle(.caption(text: "We have 4 pm tomorrow. Does that work?", at: .now))

        ["no", "afternoon", "morning"].forEach { model.handle(.recognition(.sign($0))) }
        model.handle(.recognition(.unsure))
        model.handle(.draft(turnID: 2, text: "No. In the afternoon, please. In the morning, please.", source: .template))
        model.handle(.camera(.signing))
        if self == .signing { return model }

        if let wrong = model.chips.first(where: { $0.word == "afternoon" }) {
            model.removeChip(wrong)
        }
        model.handle(.draft(turnID: 2, text: "No, sorry, 4 pm doesn't work. Is there anything tomorrow morning?", source: .llm))
        model.handle(.camera(.watching))
        model.send()

        switch self {
        case .delivered:
            model.handle(.spoken(turnID: 2))
        case .notDelivered:
            model.handle(.notDelivered(turnID: 2))
        case .ended:
            model.end()
        case .connectionLost:
            model.handle(.error(message: "Connection lost"))
        default:
            break
        }
        return model
    }
}
#endif
