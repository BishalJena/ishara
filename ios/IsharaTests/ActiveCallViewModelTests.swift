import CallSession
import XCTest
@testable import Ishara

@MainActor
final class ActiveCallViewModelTests: XCTestCase {
    private var driver: StubCallDriver!
    private var recognition: StubRecognition!
    private var model: ActiveCallViewModel!
    private var store: TurnStore { driver.store }
    private var sink: RecordingSink { driver.sink }

    override func setUp() async throws {
        driver = StubCallDriver()
        recognition = StubRecognition()
        model = ActiveCallViewModel(setup: .demo, driver: driver, recognition: recognition)
        await model.start()
        store.receive(.status(.inCall))
    }

    // MARK: Helpers

    private func sign(_ signs: Sign...) {
        signs.forEach { model.handle(.result(.sign($0))) }
    }

    private func draft(_ text: String, turn: TurnID? = nil, source: DraftSource = .llm) {
        store.receive(.draft(turnID: turn ?? store.currentTurnID, text: text, source: source))
    }

    // MARK: Starting

    func testStartPlacesTheCallForTheChosenSetup() {
        XCTAssertEqual(driver.startedWith, [.demo])
        XCTAssertTrue(model.store === store)
        XCTAssertEqual(model.phase, .live)
    }

    func testStartFailureEndsWithTheReasonAndSendsNothing() async {
        let failing = StubCallDriver()
        failing.startError = BackendError.httpStatus(403)
        let model = ActiveCallViewModel(setup: .demo, driver: failing, recognition: StubRecognition())

        await model.start()

        XCTAssertEqual(model.phase, .ended(.failed("This contact isn't on the backend's allowed list.")))
        XCTAssertFalse(model.canSend)
        XCTAssertEqual(failing.sink.sent, [])
    }

    func testEndWhileTheCallIsBeingPlacedEndsItOncePlaced() async {
        let driver = StubCallDriver()
        let model = ActiveCallViewModel(setup: .demo, driver: driver, recognition: StubRecognition())

        model.end()
        XCTAssertEqual(model.phase, .ended(.userEnded))
        await model.start()

        XCTAssertEqual(driver.sink.ends, 1)
        XCTAssertEqual(model.phase, .ended(.userEnded))
    }

    func testEndingWhileACallFailsToStartStaysUserEnded() async {
        let failing = StubCallDriver()
        failing.startError = BackendError.httpStatus(502)
        let model = ActiveCallViewModel(setup: .demo, driver: failing, recognition: StubRecognition())

        model.end()
        await model.start()

        XCTAssertEqual(model.phase, .ended(.userEnded))
    }

    func testLeaveClosesTheDriverAndStopsRecognition() {
        model.leave()

        XCTAssertEqual(driver.closeCount, 1)
        XCTAssertEqual(recognition.stopCount, 1)
        XCTAssertEqual(sink.sent, [], "leaving sends nothing")
    }

    // MARK: Recognition

    func testRecognisedSignBecomesAChipAndUnsureAQuestionMark() {
        model.handle(.result(.sign(.hello)))
        model.handle(.result(.unsure))

        XCTAssertEqual(model.chips.map(\.label), ["hello", "?"])
        XCTAssertEqual(sink.chipUpdates, [.chips(turnID: turn(1), chips: [.hello])])
    }

    func testRecognitionEventsReachTheScreenWhileTheCallRuns() async {
        let task = Task { await model.run() }
        defer { task.cancel() }
        try? await Task.sleep(for: .milliseconds(20))  // let the screen subscribe

        recognition.emit(.camera(.signing))
        recognition.emit(.result(.sign(.doctor)))

        let shown = await eventually { model.chips.map(\.label) == ["doctor"] }
        XCTAssertTrue(shown)
        XCTAssertEqual(model.cameraState, .signing)
    }

    func testCameraEventsDriveThePill() {
        model.handle(.camera(.cantSee))
        XCTAssertEqual(model.cameraState, .cantSee)
        model.handle(.camera(.watching))
        XCTAssertEqual(model.cameraState, .watching)
    }

    // MARK: SEND availability

    func testSendIsDisabledWithoutDraft() {
        XCTAssertFalse(model.canSend)
        model.send()
        XCTAssertEqual(sink.approvals, [])
    }

    func testSendIsDisabledWithBlankDraft() {
        sign(.hello)
        draft("   ")
        XCTAssertFalse(model.canSend)
        model.send()
        XCTAssertEqual(sink.approvals, [])
    }

    func testSendIsDisabledBeforeTheCallConnects() async {
        let driver = StubCallDriver()
        let connecting = ActiveCallViewModel(setup: .demo, driver: driver, recognition: StubRecognition())
        await connecting.start()
        driver.store.receive(.status(.ringing))

        connecting.choose(.yes)

        XCTAssertFalse(connecting.canSend)
        connecting.send()
        XCTAssertEqual(driver.sink.approvals, [])
    }

    func testSendApprovesExactDraftForCurrentTurn() {
        sign(.hello, .doctor, .tomorrow)
        draft("Hello, I'd like a doctor's appointment tomorrow.")
        XCTAssertTrue(model.canSend)

        model.send()

        XCTAssertEqual(sink.approvals, [.approve(turnID: turn(1), text: "Hello, I'd like a doctor's appointment tomorrow.")])
    }

    // MARK: Unsure chips

    func testUnsureChipsAreNeverSentForRecomposing() {
        sign(.yes)
        model.handle(.result(.unsure))
        sign(.thankyou)

        XCTAssertEqual(model.chips.count, 3)
        XCTAssertEqual(sink.chipUpdates, [
            .chips(turnID: turn(1), chips: [.yes]),
            .chips(turnID: turn(1), chips: [.yes, .thankyou]),
        ])
    }

    func testOnlyUnsureChipsGiveNothingToSend() {
        model.handle(.result(.unsure))
        draft("Something")
        XCTAssertNil(model.draft)
        XCTAssertFalse(model.canSend)
        XCTAssertEqual(sink.chipUpdates, [])
    }

    // MARK: Removing chips

    func testRemovingChipRecomposesWithRemainingWords() throws {
        sign(.no, .afternoon, .morning)
        let wrong = try XCTUnwrap(model.chips.first { $0.sign == .afternoon })

        model.removeChip(wrong)

        XCTAssertEqual(model.chips.compactMap(\.sign), [.no, .morning])
        XCTAssertEqual(sink.chipUpdates.last, .chips(turnID: turn(1), chips: [.no, .morning]))
        XCTAssertEqual(sink.chipUpdates.count, 4)
    }

    func testRemovingLastRecognisedChipClearsDraft() throws {
        sign(.hello)
        draft("Hello.")
        let chip = try XCTUnwrap(model.chips.first)

        model.removeChip(chip)

        XCTAssertNil(model.draft)
        XCTAssertFalse(model.canSend)
        XCTAssertEqual(sink.chipUpdates, [.chips(turnID: turn(1), chips: [.hello])])
    }

    func testRemovingUnsureChipDoesNotRecompose() throws {
        sign(.yes)
        model.handle(.result(.unsure))
        let unsure = try XCTUnwrap(model.chips.first { $0.sign == nil })

        model.removeChip(unsure)

        XCTAssertEqual(model.chips.compactMap(\.sign), [.yes])
        XCTAssertEqual(sink.chipUpdates.count, 1)
    }

    // MARK: Single use SEND

    func testSendIsSingleUseAndWipesChipsAndDraft() {
        sign(.hello)
        draft("Hello.")

        model.send()
        model.send()

        XCTAssertEqual(sink.approvals.count, 1)
        XCTAssertTrue(model.chips.isEmpty)
        XCTAssertNil(model.draft)
        XCTAssertFalse(model.canSend)
        XCTAssertEqual(store.currentTurnID, turn(2))
        XCTAssertEqual(model.delivery, .speaking(text: "Hello."))
    }

    func testSendIsBlockedWhileSpeakingEvenWithNewDraft() {
        sign(.hello)
        draft("Hello.")
        model.send()

        sign(.doctor)
        draft("I'd like to see a doctor.")
        model.send()

        XCTAssertEqual(sink.approvals.count, 1)
    }

    func testSpokenConfirmationMarksDeliveredAndAddsTranscript() {
        sign(.hello)
        draft("Hello.")
        model.send()

        store.receive(.spoken(turnID: turn(1)))

        XCTAssertEqual(model.delivery, .delivered)
        XCTAssertEqual(model.captions.last?.speaker, .user)
        XCTAssertEqual(model.captions.last?.text, "Hello.")
    }

    func testSpokenForAnotherTurnIsIgnored() {
        sign(.hello)
        draft("Hello.")
        model.send()

        store.receive(.spoken(turnID: turn(7)))

        XCTAssertTrue(model.isSpeaking)
        XCTAssertTrue(model.captions.isEmpty)
    }

    func testDeliveryResultShowsUntilTheNextReplyStarts() {
        sign(.hello)
        draft("Hello.")
        model.send()
        store.receive(.spoken(turnID: turn(1)))
        XCTAssertTrue(model.showsDeliveryResult)

        sign(.yes)

        XCTAssertFalse(model.showsDeliveryResult)
    }

    // MARK: Stale drafts

    func testDraftForStaleTurnIsIgnored() {
        sign(.hello)
        draft("Hello.")
        model.send()

        sign(.doctor)
        draft("Old text from turn one", turn: turn(1))

        XCTAssertNil(model.draft)
    }

    func testDraftForFutureTurnIsIgnored() {
        sign(.hello)
        draft("Hello.", turn: turn(5))
        XCTAssertNil(model.draft)
    }

    func testLateDraftAfterClearIsIgnored() {
        sign(.hello)
        model.clear()
        draft("Hello.", turn: turn(1))

        XCTAssertNil(model.draft)
        XCTAssertTrue(model.chips.isEmpty)
        XCTAssertEqual(sink.chipUpdates, [.chips(turnID: turn(1), chips: [.hello])], "Clear sends nothing")
    }

    // MARK: Quick replies

    func testQuickRepliesInsertExactSentences() {
        let expected: [QuickReply: String] = [
            .yes: "Yes.",
            .no: "No.",
            .wait: "Please wait a moment, I'm signing my reply.",
            .repeat: "Sorry, could you please repeat that?",
        ]
        for (reply, sentence) in expected {
            model.choose(reply)
            XCTAssertEqual(model.draft, DraftDisplay(text: sentence, badge: .quickReply), "\(reply)")
        }
        XCTAssertEqual(sink.approvals, [], "A quick reply must not send by itself")
    }

    func testQuickReplyIsNotOverwrittenByLateComposerDraft() {
        sign(.no)
        model.choose(.repeat)
        draft("No.", turn: turn(1))
        draft("No.")

        XCTAssertEqual(model.draft?.text, "Sorry, could you please repeat that?")
    }

    func testQuickReplySendsExactSentence() {
        model.choose(.wait)
        model.send()
        XCTAssertEqual(sink.approvals, [.approve(turnID: turn(2), text: "Please wait a moment, I'm signing my reply.")])
    }

    func testQuickRepliesAreOffWhileAReplyIsBeingSpoken() {
        model.choose(.yes)
        model.send()

        model.choose(.no)

        XCTAssertFalse(model.canUseQuickReplies)
        XCTAssertNil(model.draft)
    }

    // MARK: Not delivered

    func testNotDeliveredOffersResendWithoutSending() {
        sign(.no, .morning)
        draft("No, sorry. Is tomorrow morning possible?")
        model.send()

        store.receive(.notDelivered(turnID: turn(1), reason: "no_confirmation"))

        XCTAssertEqual(model.delivery, .notDelivered(text: "No, sorry. Is tomorrow morning possible?"))
        XCTAssertEqual(model.draft, DraftDisplay(text: "No, sorry. Is tomorrow morning possible?", badge: .notDelivered))
        XCTAssertTrue(model.canSend)
        XCTAssertEqual(sink.approvals.count, 1, "Must never resend by itself")
    }

    func testResendAfterNotDeliveredUsesNewTurn() {
        sign(.no)
        draft("No.")
        model.send()
        store.receive(.notDelivered(turnID: turn(1), reason: "no_confirmation"))

        model.send()

        XCTAssertEqual(sink.approvals, [.approve(turnID: turn(1), text: "No."), .approve(turnID: turn(3), text: "No.")])
    }

    func testRetryIsNotOfferedOnceANewReplyIsStarted() {
        sign(.no)
        draft("No.")
        model.send()
        store.receive(.notDelivered(turnID: turn(1), reason: "no_confirmation"))

        sign(.morning)

        XCTAssertNil(model.retryText)
        XCTAssertNil(model.draft)
        XCTAssertFalse(model.canSend)
        model.send()
        XCTAssertEqual(sink.approvals.count, 1, "old text is never resent over new chips")
    }

    func testStopBeforeSpeakingShowsStoppedAndOffersSendOnlyOnTap() {
        model.choose(.yes)
        model.send()
        model.stop()

        store.receive(.notDelivered(turnID: turn(2), reason: "stopped"))

        XCTAssertEqual(model.delivery, .stopped(text: "Yes."))
        XCTAssertEqual(model.draft, DraftDisplay(text: "Yes.", badge: .stopped))
        XCTAssertTrue(model.canSend)
        XCTAssertEqual(sink.approvals.count, 1, "Must never resend by itself")
        model.send()
        XCTAssertEqual(sink.approvals.last, .approve(turnID: turn(4), text: "Yes."))
    }

    func testStopAsksOnceWhileSpeaking() {
        model.stop()
        XCTAssertEqual(sink.stops, 0)

        model.choose(.yes)
        model.send()
        model.stop()
        model.stop()

        XCTAssertEqual(sink.stops, 1)
        XCTAssertTrue(model.isStopRequested)
    }

    // MARK: Ending

    func testEndMovesToEndedAndSendsNothingFurther() {
        sign(.hello)
        draft("Hello.")

        model.end()

        XCTAssertEqual(model.phase, .ended(.userEnded))
        XCTAssertEqual(sink.ends, 1)
        XCTAssertTrue(model.chips.isEmpty)
        XCTAssertNil(model.draft)

        let messagesAtEnd = sink.sent
        model.choose(.yes)
        model.send()
        model.end()
        model.handle(.result(.sign(.doctor)))
        draft("Hello.", turn: turn(1))
        model.send()

        XCTAssertEqual(sink.sent, messagesAtEnd)
        XCTAssertFalse(model.canSend)
    }

    func testLateEventsCannotReviveEndedCall() {
        store.receive(.caption(text: "City Clinic, how can I help?", at: 1))
        model.end()

        store.receive(.status(.inCall))
        store.receive(.caption(text: "Hello?", at: 2))
        model.choose(.yes)
        model.send()

        XCTAssertEqual(model.phase, .ended(.userEnded))
        XCTAssertEqual(model.captions.map(\.text), ["City Clinic, how can I help?"], "no caption is added after End")
        XCTAssertEqual(sink.approvals, [])
    }

    func testEndKeepsTheTranscript() {
        store.receive(.caption(text: "City Clinic, how can I help?", at: 1))
        model.choose(.yes)
        model.send()
        store.receive(.spoken(turnID: turn(2)))

        model.end()

        XCTAssertEqual(model.captions.map(\.text), ["City Clinic, how can I help?", "Yes."])
        XCTAssertTrue(model.isCallOver)
    }

    func testCallIsOverOnlyOnceItCannotComeBack() {
        XCTAssertFalse(model.isCallOver)
        store.connectionLost()
        XCTAssertFalse(model.isCallOver, "a reconnect may still bring the call back")

        driver.onReconnectStopped?(.attemptsUsedUp)

        XCTAssertTrue(model.isCallOver)
    }

    func testRemoteEndWipesPendingReply() {
        model.choose(.yes)
        model.send()

        store.receive(.status(.ended))

        XCTAssertEqual(model.phase, .ended(.remoteEnded))
        XCTAssertEqual(model.delivery, .idle)
        store.receive(.spoken(turnID: turn(2)))
        XCTAssertTrue(model.captions.isEmpty)
    }

    func testLostConnectionGoesSilentAndKeepsEndAvailable() {
        sign(.hello)
        draft("Hello.")

        store.connectionLost()

        XCTAssertEqual(model.phase, .interrupted("Nothing will be sent"))
        XCTAssertFalse(model.isEnded, "End stays available while reconnecting")
        XCTAssertNil(model.draft)
        model.send()
        XCTAssertEqual(sink.approvals, [])
    }

    // MARK: Captions

    func testCaptionKeepsDraft() {
        sign(.no)
        draft("No.")

        store.receive(.caption(text: "Are you still there?", at: 1))

        XCTAssertEqual(model.draft?.text, "No.")
        XCTAssertEqual(model.captions.map(\.text), ["Are you still there?"])
    }
}
