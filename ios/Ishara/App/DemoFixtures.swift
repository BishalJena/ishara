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
    /// What `notes()` returns; without it, there was no call.
    var fixedNotes: CallNotes?

    var onReconnectStopped: ((ReconnectStop) -> Void)?

    func start(_ setup: CallSetup) async throws -> TurnStore { store }
    func close() {}
    func createBrief(_ request: BriefRequest) async throws -> Brief { DelegatedDemo.brief(for: request) }
    func notes() async throws -> CallNotes {
        guard let fixedNotes else { throw CallDriverError.noCall }
        return fixedNotes
    }
}

extension DemoFixture {
    /// The Notes screen after the scripted delegated call was booked on a "yes", with an
    /// automatic summary standing in for the one Bolna's webhook delivers.
    @MainActor
    func makeNotes() -> NotesModel? {
        guard self == .notes else { return nil }
        let setup = CallSetup.demo
        let brief = DelegatedDemo.brief(for: BriefRequest(
            purpose: setup.purpose, chips: [.tomorrow, .morning], profile: Profile(name: setup.details.name)))
        let answer = DelegatedDemo.options[0].spoken
        let now = Date().timeIntervalSince1970
        let transcript = [
            TranscriptEntry(speaker: .agent, text: DemoScript.disclosure, at: now),
            TranscriptEntry(speaker: .receptionist, text: DelegatedDemo.offer, at: now),
            TranscriptEntry(speaker: .agent, text: answer, at: now),
            TranscriptEntry(speaker: .receptionist, text: DelegatedDemo.confirmation, at: now),
        ]
        var notes = DelegatedDemo.notes(
            goal: brief.goal, name: setup.details.name, brief: brief.text,
            transcript: transcript, answers: [answer], ready: true)
        notes.bolnaSummary = "The caller booked a doctor's appointment for 10:30 tomorrow morning."
        let driver = FixtureCallDriver()
        driver.fixedNotes = notes
        return NotesModel(contactName: setup.contact.name, driver: driver)
    }

    /// Builds the call screen state by replaying PLAN §1 messages into a real TurnStore.
    @MainActor
    func makeActiveCall() -> ActiveCallViewModel? {
        guard self != .home, self != .getReady, self != .notes else { return nil }
        let driver = FixtureCallDriver()
        let store = driver.store
        let model = ActiveCallViewModel(setup: .demo, driver: driver, recognition: ScriptedRecognitionController())
        model.attach(store)

        store.receive(.status(.inCall))
        if self == .endedNoCaptions {
            model.end()
            return model
        }
        store.receive(.caption(text: DemoScript.disclosure, at: Date().timeIntervalSince1970, speaker: .agent))
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
        if self == .composing { return model }
        store.receive(.draft(turnID: store.currentTurnID, text: "No, sorry, 4 pm doesn't work. Is there anything tomorrow morning?", source: .llm))
        model.handle(.camera(.watching))
        let secondTurn = store.currentTurnID
        store.send()

        switch self {
        case .delivered:
            store.receive(.spoken(turnID: secondTurn))
        case .notDelivered:
            store.receive(.notDelivered(turnID: secondTurn, reason: "no_confirmation"))
        case .deliveredDespiteStop:
            model.stop()
            store.receive(.error(code: ServerError.cannotInterrupt, message: "Bolna is already speaking."))
            store.receive(.spoken(turnID: secondTurn))
        case .stopped:
            model.stop()
            store.receive(.notDelivered(turnID: secondTurn, reason: "stopped"))
        case .stopTooLate:
            model.stop()
            store.receive(.error(code: ServerError.cannotInterrupt, message: "Bolna is already speaking."))
        case .backendError:
            store.receive(.notDelivered(turnID: secondTurn, reason: "no_confirmation"))
            store.add(.recognised(.yes))
            store.receive(.error(code: "stale_turn", message: "That turn is closed; start a new one."))
        case .ended, .hangUpUnconfirmed:
            store.receive(.caption(text: "Yes, 10:30 tomorrow morning.", at: Date().timeIntervalSince1970))
            store.receive(.caption(text: DemoScript.goodbye, at: Date().timeIntervalSince1970, speaker: .agent))
            model.end()
            if self == .hangUpUnconfirmed {
                store.receive(.error(code: ServerError.endFailed, message: "Could not reach Bolna to hang up."))
            }
        case .connectionLost:
            store.connectionLost()
        default:
            break
        }
        return model
    }
}
#endif
