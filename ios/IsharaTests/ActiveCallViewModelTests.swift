import XCTest
@testable import Ishara

@MainActor
final class ActiveCallViewModelTests: XCTestCase {
    private var driver: RecordingCallDriver!
    private var model: ActiveCallViewModel!

    override func setUp() async throws {
        driver = RecordingCallDriver()
        model = ActiveCallViewModel(setup: .demo, driver: driver)
        model.handle(.status(.inCall))
    }

    // MARK: Helpers

    private func sign(_ words: String...) {
        words.forEach { model.handle(.recognition(.sign($0))) }
    }

    private func draft(_ text: String, turn: TurnID? = nil, source: DraftSource = .llm) {
        model.handle(.draft(turnID: turn ?? model.currentTurnID, text: text, source: source))
    }

    // MARK: SEND availability

    func testSendIsDisabledWithoutDraft() {
        XCTAssertFalse(model.canSend)
        model.send()
        XCTAssertTrue(driver.approvals.isEmpty)
    }

    func testSendIsDisabledWithBlankDraft() {
        sign("hello")
        draft("   ")
        XCTAssertFalse(model.canSend)
        model.send()
        XCTAssertTrue(driver.approvals.isEmpty)
    }

    func testSendIsDisabledBeforeTheCallConnects() {
        let connecting = ActiveCallViewModel(setup: .demo, driver: driver)
        connecting.handle(.status(.ringing))
        connecting.choose(.yes)
        XCTAssertFalse(connecting.canSend)
        connecting.send()
        XCTAssertTrue(driver.approvals.isEmpty)
    }

    func testSendApprovesExactDraftForCurrentTurn() {
        sign("hello", "doctor", "tomorrow")
        draft("Hello, I'd like a doctor's appointment tomorrow.")
        XCTAssertTrue(model.canSend)

        model.send()

        XCTAssertEqual(driver.approvals, [.init(turnID: 1, text: "Hello, I'd like a doctor's appointment tomorrow.")])
    }

    // MARK: Unsure chips

    func testUnsureChipsAreNeverSentForRecomposing() {
        sign("yes")
        model.handle(.recognition(.unsure))
        sign("thankyou")

        XCTAssertEqual(model.chips.count, 3)
        XCTAssertEqual(driver.chipUpdates.map(\.words), [["yes"], ["yes", "thankyou"]])
        XCTAssertFalse(driver.chipUpdates.contains { $0.words.contains { $0.contains("?") } })
    }

    func testOnlyUnsureChipsGiveNothingToSend() {
        model.handle(.recognition(.unsure))
        draft("Something")
        XCTAssertNil(model.draft)
        XCTAssertFalse(model.canSend)
        XCTAssertTrue(driver.chipUpdates.isEmpty)
    }

    // MARK: Removing chips

    func testRemovingChipRecomposesWithRemainingWords() throws {
        sign("no", "afternoon", "morning")
        let wrong = try XCTUnwrap(model.chips.first { $0.word == "afternoon" })

        model.removeChip(wrong)

        XCTAssertEqual(model.chips.compactMap(\.word), ["no", "morning"])
        XCTAssertEqual(driver.chipUpdates.last, .init(turnID: 1, words: ["no", "morning"]))
        XCTAssertEqual(driver.chipUpdates.count, 4)
    }

    func testRemovingLastRecognisedChipClearsDraft() throws {
        sign("hello")
        draft("Hello.")
        let chip = try XCTUnwrap(model.chips.first)

        model.removeChip(chip)

        XCTAssertNil(model.draft)
        XCTAssertFalse(model.canSend)
        XCTAssertEqual(driver.chipUpdates.last, .init(turnID: 1, words: []))
    }

    func testRemovingUnsureChipDoesNotRecompose() throws {
        sign("yes")
        model.handle(.recognition(.unsure))
        let unsure = try XCTUnwrap(model.chips.first { $0.word == nil })

        model.removeChip(unsure)

        XCTAssertEqual(model.chips.compactMap(\.word), ["yes"])
        XCTAssertEqual(driver.chipUpdates.count, 1)
    }

    // MARK: Single use SEND

    func testSendIsSingleUseAndWipesChipsAndDraft() {
        sign("hello")
        draft("Hello.")

        model.send()
        model.send()

        XCTAssertEqual(driver.approvals.count, 1)
        XCTAssertTrue(model.chips.isEmpty)
        XCTAssertNil(model.draft)
        XCTAssertFalse(model.canSend)
        XCTAssertEqual(model.currentTurnID, 2)
        XCTAssertEqual(model.delivery, .speaking(turnID: 1, draft: Draft(text: "Hello.", source: .llm)))
    }

    func testSendIsBlockedWhileSpeakingEvenWithNewDraft() {
        sign("hello")
        draft("Hello.")
        model.send()

        sign("doctor")
        draft("I'd like to see a doctor.")
        model.send()

        XCTAssertEqual(driver.approvals.count, 1)
    }

    func testSpokenConfirmationMarksDeliveredAndAddsTranscript() {
        sign("hello")
        draft("Hello.")
        model.send()

        model.handle(.spoken(turnID: 1))

        XCTAssertEqual(model.delivery, .delivered(text: "Hello."))
        XCTAssertEqual(model.captions.last?.speaker, .user)
        XCTAssertEqual(model.captions.last?.text, "Hello.")
    }

    func testSpokenForAnotherTurnIsIgnored() {
        sign("hello")
        draft("Hello.")
        model.send()

        model.handle(.spoken(turnID: 7))

        XCTAssertTrue(model.isSpeaking)
        XCTAssertTrue(model.captions.isEmpty)
    }

    // MARK: Stale drafts

    func testDraftForStaleTurnIsIgnored() {
        sign("hello")
        draft("Hello.")
        model.send()

        sign("doctor")
        draft("Old text from turn one", turn: 1)

        XCTAssertNil(model.draft)
    }

    func testDraftForFutureTurnIsIgnored() {
        sign("hello")
        draft("Hello.", turn: 5)
        XCTAssertNil(model.draft)
    }

    func testLateDraftAfterClearIsIgnored() {
        sign("hello")
        model.clear()
        draft("Hello.")

        XCTAssertNil(model.draft)
        XCTAssertTrue(model.chips.isEmpty)
        XCTAssertEqual(driver.chipUpdates.last, .init(turnID: 1, words: []))
    }

    // MARK: Quick replies

    func testQuickRepliesInsertExactSentences() {
        let expected: [QuickReply: String] = [
            .yes: "Yes.",
            .no: "No.",
            .wait: "Please wait a moment, I'm signing my reply.",
            .repeatThat: "Sorry, could you please repeat that?",
        ]
        for (reply, sentence) in expected {
            model.choose(reply)
            XCTAssertEqual(model.draft, Draft(text: sentence, source: .quickReply), "\(reply)")
        }
        XCTAssertTrue(driver.approvals.isEmpty, "A quick reply must not send by itself")
    }

    func testQuickReplyIsNotOverwrittenByLateComposerDraft() {
        sign("no")
        model.choose(.repeatThat)
        draft("No.")

        XCTAssertEqual(model.draft?.text, "Sorry, could you please repeat that?")
    }

    func testQuickReplySendsExactSentence() {
        model.choose(.wait)
        model.send()
        XCTAssertEqual(driver.approvals, [.init(turnID: 1, text: "Please wait a moment, I'm signing my reply.")])
    }

    // MARK: Not delivered

    func testNotDeliveredOffersResendWithoutSending() {
        sign("no", "morning")
        draft("No, sorry. Is tomorrow morning possible?")
        model.send()

        model.handle(.notDelivered(turnID: 1))

        XCTAssertEqual(model.delivery, .notDelivered(text: "No, sorry. Is tomorrow morning possible?"))
        XCTAssertEqual(model.draft?.text, "No, sorry. Is tomorrow morning possible?")
        XCTAssertTrue(model.canSend)
        XCTAssertEqual(driver.approvals.count, 1, "Must never resend by itself")
    }

    func testResendAfterNotDeliveredUsesNewTurn() {
        sign("no")
        draft("No.")
        model.send()
        model.handle(.notDelivered(turnID: 1))

        model.send()

        XCTAssertEqual(driver.approvals, [.init(turnID: 1, text: "No."), .init(turnID: 2, text: "No.")])
    }

    func testStopAsksDriverOnceWhileSpeaking() {
        model.stop()
        XCTAssertEqual(driver.stopCount, 0)

        model.choose(.yes)
        model.send()
        model.stop()
        model.stop()

        XCTAssertEqual(driver.stopCount, 1)
        XCTAssertTrue(model.isStopRequested)
    }

    // MARK: Ending

    func testEndMovesToEndedAndSendsNothingFurther() {
        sign("hello")
        draft("Hello.")

        model.end()

        XCTAssertEqual(model.phase, .ended(.userEnded))
        XCTAssertEqual(driver.endCount, 1)
        XCTAssertTrue(model.chips.isEmpty)
        XCTAssertNil(model.draft)

        let commandsAtEnd = driver.commandCount
        model.choose(.yes)
        model.send()
        model.end()
        model.handle(.recognition(.sign("doctor")))
        model.handle(.draft(turnID: 1, text: "Hello.", source: .llm))
        model.send()

        XCTAssertEqual(driver.commandCount, commandsAtEnd)
        XCTAssertTrue(driver.approvals.isEmpty)
        XCTAssertFalse(model.canSend)
    }

    func testLateEventsCannotReviveEndedCall() {
        model.end()

        model.handle(.status(.inCall))
        model.handle(.caption(text: "Hello?", at: .now))
        model.choose(.yes)
        model.send()

        XCTAssertEqual(model.phase, .ended(.userEnded))
        XCTAssertTrue(model.captions.isEmpty)
        XCTAssertTrue(driver.approvals.isEmpty)
    }

    func testRemoteEndWipesPendingReply() {
        model.choose(.yes)
        model.send()

        model.handle(.status(.ended))

        XCTAssertEqual(model.phase, .ended(.remoteEnded))
        XCTAssertEqual(model.delivery, .idle)
        model.handle(.spoken(turnID: 1))
        XCTAssertTrue(model.captions.isEmpty)
    }

    func testNetworkErrorEndsCallSilently() {
        sign("hello")
        draft("Hello.")

        model.handle(.error(message: "Connection lost"))

        XCTAssertEqual(model.phase, .ended(.failed("Connection lost")))
        XCTAssertNil(model.draft)
        model.send()
        XCTAssertTrue(driver.approvals.isEmpty)
    }

    // MARK: Captions

    func testCaptionKeepsDraft() {
        sign("no")
        draft("No.")

        model.handle(.caption(text: "Are you still there?", at: .now))

        XCTAssertEqual(model.draft?.text, "No.")
        XCTAssertEqual(model.captions.map(\.text), ["Are you still there?"])
    }
}
