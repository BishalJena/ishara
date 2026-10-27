import XCTest

@testable import CallSession

/// Decision D9, attended delegated call: the agent's question is shown, answered by tap or
/// by a recognised yes/no/wait, and closed by `ask_resolved`.
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
