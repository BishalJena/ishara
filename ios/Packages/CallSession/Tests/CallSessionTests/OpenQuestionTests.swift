import XCTest

@testable import CallSession

/// Decision D9, attended delegated call: the agent's question is shown, answered by tap or
/// by a recognised sign equal to one of its options, and closed by `ask_resolved`.
@MainActor
final class OpenQuestionTests: XCTestCase {
    private var sink: FakeSink!
    private var store: TurnStore!
    private let ask = ServerMessage.ask(
        askID: "a1", question: "We have 4 pm tomorrow. Does that work?",
        options: [
            AskOption(choice: .yes, spoken: "Yes, 4 pm tomorrow works. Thank you."),
            AskOption(choice: .no, spoken: "No, sorry."),
            AskOption(choice: .wait, spoken: "One moment, please."),
        ],
        fallback: "I'll call back.", timeoutS: 10)

    override func setUp() async throws {
        sink = FakeSink()
        let ids = SequentialTurnIDs()
        store = TurnStore(sink: sink, initialState: .inCall, makeTurnID: { ids.make() })
    }

    func testAskOpensAQuestionWithItsOptions() {
        store.receive(ask)
        XCTAssertEqual(store.openQuestion?.askID, "a1")
        XCTAssertEqual(store.openQuestion?.spoken(for: .yes), "Yes, 4 pm tomorrow works. Thank you.")
    }

    func testTapAnswerSendsTheChoiceAndNothingElse() {
        store.receive(ask)
        XCTAssertTrue(store.answer(.no))
        XCTAssertEqual(sink.sent, [.answer(askID: "a1", choice: .no)])
    }

    func testRecognisedYesAnswersTheQuestionInsteadOfBecomingAChip() {
        store.receive(ask)
        XCTAssertTrue(store.answerIfAsked(.yes))
        XCTAssertEqual(sink.sent, [.answer(askID: "a1", choice: .yes)])
        XCTAssertTrue(store.chips.isEmpty)
        // Other signs are not answers.
        XCTAssertFalse(store.answerIfAsked(.tomorrow))
    }

    /// Version B: an open "when?" question offers time words; signing one answers it.
    private let timeAsk = ServerMessage.ask(
        askID: "t1", question: "what time would you like to come in",
        options: [
            AskOption(choice: .tomorrow, spoken: "Tomorrow, please. What times are available?"),
            AskOption(choice: .morning, spoken: "In the morning, please. What times are available?"),
            AskOption(choice: .now, spoken: "Today, as soon as possible, please. What times are available?"),
            AskOption(choice: .wait, spoken: "One moment, please, I'm checking."),
        ],
        fallback: "I'll call back.", timeoutS: 10)

    func testRecognisedTimeWordAnswersAnOpenTimeQuestion() {
        store.receive(timeAsk)
        XCTAssertTrue(store.answerIfAsked(.tomorrow))
        XCTAssertEqual(sink.sent, [.answer(askID: "t1", choice: .tomorrow)])
        XCTAssertTrue(store.chips.isEmpty)
    }

    /// Only a sign equal to one of the open question's options answers it: a yes is no
    /// answer to "what time?", and a time word none to "does 4 pm work?".
    func testASignThatIsNoOptionAnswersNothing() {
        store.receive(timeAsk)
        XCTAssertFalse(store.answerIfAsked(.yes))
        XCTAssertFalse(store.answer(.no))
        XCTAssertFalse(store.answerIfAsked(.today))
        store.receive(ask)
        XCTAssertFalse(store.answerIfAsked(.now))
        XCTAssertFalse(store.answer(.morning))
        XCTAssertEqual(sink.sent, [])
    }

    /// Every answer word is a sign, so the recognizer can chip it.
    func testEveryChoiceIsASign() {
        for choice in AskChoice.allCases {
            XCTAssertNotNil(Sign(rawValue: choice.rawValue), choice.rawValue)
        }
    }

    func testWithoutAnOpenQuestionNothingIsSent() {
        XCTAssertFalse(store.answer(.yes))
        XCTAssertFalse(store.answerIfAsked(.yes))
        XCTAssertEqual(sink.sent, [])
    }

    func testResolvedClosesTheQuestionAndRecordsWhatWasSaid() {
        store.receive(ask)
        store.receive(.askResolved(askID: "a1", spoken: "Yes, 4 pm tomorrow works. Thank you.", source: "user"))
        XCTAssertNil(store.openQuestion)
        XCTAssertEqual(store.captions.last?.text, "Yes, 4 pm tomorrow works. Thank you.")
        XCTAssertEqual(store.captions.last?.speaker, .user)
        store.receive(ask)
        store.receive(.askResolved(askID: "a1", spoken: "I'll call back.", source: "timeout"))
        XCTAssertEqual(store.captions.last?.speaker, .agent)
    }

    /// A lost connection wipes the question like a draft: the backend may resolve it (its
    /// timeout line) while the app can't hear, so an answer tapped later could be stale.
    func testLostConnectionWipesTheQuestionAndAnswersNothing() {
        store.receive(ask)
        store.connectionLost()

        XCTAssertNil(store.openQuestion)
        XCTAssertFalse(store.answer(.yes))
        XCTAssertFalse(store.answerIfAsked(.yes))
        XCTAssertEqual(sink.sent, [])
    }

    func testQuestionStaysGoneAfterTheConnectionComesBack() {
        store.receive(ask)
        store.receive(.status(.error))
        store.receive(.status(.inCall))

        XCTAssertNil(store.openQuestion)
        XCTAssertFalse(store.answer(.no))
        XCTAssertEqual(sink.sent, [])
    }

    func testEndedCallAnswersNothing() {
        store.receive(ask)
        store.receive(.status(.ended))
        XCTAssertNil(store.openQuestion, "an ended call still shows the question")
        XCTAssertFalse(store.answer(.yes))
        XCTAssertFalse(sink.sent.contains(.answer(askID: "a1", choice: .yes)))
    }
}
