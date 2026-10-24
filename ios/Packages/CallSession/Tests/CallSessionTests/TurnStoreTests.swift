import XCTest

@testable import CallSession

@MainActor
final class FakeSink: OutgoingMessageSink {
    private(set) var sent: [AppMessage] = []
    /// Every call, in order, so tests can check `discardPending` ran before `end`.
    private(set) var log: [String] = []

    func send(_ message: AppMessage) {
        sent.append(message)
        log.append("send")
    }

    func discardPending() {
        log.append("discard")
    }

    var approvals: [AppMessage] {
        sent.filter { if case .approve = $0 { true } else { false } }
    }
}

/// turn1, turn2, ... so tests can name the turn a message belongs to.
@MainActor
final class SequentialTurnIDs {
    private var next = 1
    func make() -> TurnID {
        defer { next += 1 }
        return TurnID("turn\(next)")!
    }
}

@MainActor
final class TurnStoreTests: XCTestCase {
    private var sink: FakeSink!
    private var store: TurnStore!

    override func setUp() async throws {
        sink = FakeSink()
        let ids = SequentialTurnIDs()
        store = TurnStore(sink: sink, initialState: .inCall, makeTurnID: { ids.make() })
    }

    private func turn(_ n: Int) -> TurnID { TurnID("turn\(n)")! }

    private func showDraft(_ text: String = "Hello, I'd like a doctor's appointment tomorrow.") {
        store.add(.recognised(.hello))
        store.receive(.draft(turnID: store.currentTurnID, text: text, source: .llm))
    }

    // MARK: Chips

    func testRecognisedChipsAreSentForTheCurrentTurn() {
        store.add(.recognised(.hello))
        store.add(.recognised(.doctor))

        XCTAssertEqual(
            sink.sent,
            [.chips(turnID: turn(1), chips: [.hello]),
             .chips(turnID: turn(1), chips: [.hello, .doctor])])
    }

    func testUnsureChipIsShownButNeverSent() {
        store.add(.recognised(.no))
        store.add(.unsure())
        store.add(.recognised(.morning))

        XCTAssertEqual(store.chips.count, 3)
        XCTAssertEqual(
            sink.sent,
            [.chips(turnID: turn(1), chips: [.no]),
             .chips(turnID: turn(1), chips: [.no, .morning])])
    }

    func testOnlyUnsureChipsSendNothing() {
        store.add(.unsure())
        store.add(.unsure())

        XCTAssertEqual(store.chips.count, 2)
        XCTAssertEqual(sink.sent, [])
    }

    func testRemovingAChipResendsTheRemainingChips() {
        store.add(.recognised(.no))
        let wrong = Chip.recognised(.evening)
        store.add(wrong)
        store.add(.recognised(.morning))

        store.remove(wrong)

        XCTAssertEqual(sink.sent.last, .chips(turnID: turn(1), chips: [.no, .morning]))
        XCTAssertEqual(store.recognisedSigns, [.no, .morning])
    }

    func testRemovingTheLastRecognisedChipSendsNothingAndClearsDraft() {
        let only = Chip.recognised(.hello)
        store.add(only)
        store.receive(.draft(turnID: turn(1), text: "Hello.", source: .template))

        store.remove(only)

        XCTAssertEqual(sink.sent, [.chips(turnID: turn(1), chips: [.hello])])
        XCTAssertNil(store.draft)
        XCTAssertFalse(store.canSend)
    }

    func testRemovingAnUnsureChipSendsNothing() {
        store.add(.recognised(.yes))
        let unsure = Chip.unsure()
        store.add(unsure)

        store.remove(unsure)

        XCTAssertEqual(sink.sent, [.chips(turnID: turn(1), chips: [.yes])])
        XCTAssertEqual(store.chips.count, 1)
    }

    func testChipChangeClearsTheOldDraft() {
        showDraft("Hello.")

        store.add(.recognised(.doctor))

        XCTAssertNil(store.draft, "the old draft no longer matches the chips")
    }

    func testNinthRecognisedChipIsRefused() {
        for _ in 0..<ProtocolLimits.maxChips {
            XCTAssertTrue(store.add(.recognised(.yes)))
        }

        XCTAssertFalse(store.add(.recognised(.no)))

        XCTAssertEqual(store.recognisedSigns.count, ProtocolLimits.maxChips)
        XCTAssertEqual(sink.sent.count, ProtocolLimits.maxChips)
        if case let .chips(_, chips) = sink.sent.last {
            XCTAssertEqual(chips.count, ProtocolLimits.maxChips)
        } else {
            XCTFail("expected chips")
        }
    }

    // MARK: Clear

    func testClearWipesChipsAndDraftOnAFreshTurnWithoutSending() {
        showDraft("Hello.")
        store.add(.unsure())
        let sentBefore = sink.sent

        store.clear()

        XCTAssertEqual(store.chips, [])
        XCTAssertNil(store.draft)
        XCTAssertEqual(store.currentTurnID, turn(2))
        XCTAssertEqual(sink.sent, sentBefore)
    }

    func testLateDraftAfterClearIsIgnored() {
        store.add(.recognised(.hello))
        store.clear()
        store.add(.recognised(.yes))

        store.receive(.draft(turnID: turn(1), text: "Hello.", source: .llm))

        XCTAssertNil(store.draft, "a draft for the cleared chips is stale")
        XCTAssertEqual(sink.sent.last, .chips(turnID: turn(2), chips: [.yes]))
    }

    func testClearWithNothingToClearKeepsTheTurn() {
        store.clear()

        XCTAssertEqual(store.currentTurnID, turn(1))
    }

    // MARK: Drafts

    func testDraftForTheCurrentTurnIsShown() {
        store.add(.recognised(.hello))

        store.receive(.draft(turnID: turn(1), text: "Hello.", source: .llm))

        XCTAssertEqual(store.draft, Draft(text: "Hello.", origin: .llm))
        XCTAssertTrue(store.canSend)
    }

    func testTemplateDraftKeepsItsOrigin() {
        store.add(.recognised(.hello))

        store.receive(.draft(turnID: turn(1), text: "Hello.", source: .template))

        XCTAssertEqual(store.draft?.origin, .template)
    }

    func testDraftForAnotherTurnIsIgnored() {
        store.add(.recognised(.hello))

        store.receive(.draft(turnID: TurnID("someOtherTurn")!, text: "Hello.", source: .llm))

        XCTAssertNil(store.draft)
    }

    func testDraftForAnOldTurnIsIgnoredAfterSend() {
        showDraft("Hello.")
        store.send()
        store.add(.recognised(.no))

        store.receive(.draft(turnID: turn(1), text: "Hello.", source: .llm))

        XCTAssertNil(store.draft)
    }

    func testDraftIsIgnoredWhenNoRecognisedChipsRemain() {
        store.add(.unsure())

        store.receive(.draft(turnID: turn(1), text: "Hello.", source: .llm))

        XCTAssertNil(store.draft)
    }

    func testLateBackendDraftDoesNotReplaceQuickReply() {
        store.add(.recognised(.hello))
        store.useQuickReply(.wait)

        store.receive(.draft(turnID: turn(1), text: "Hello.", source: .llm))
        store.receive(.draft(turnID: turn(2), text: "Hello.", source: .llm))

        XCTAssertEqual(store.draft, Draft(text: QuickReply.wait.text, origin: .quickReply))
    }

    // MARK: Quick replies

    func testQuickReplyTexts() {
        XCTAssertEqual(QuickReply.yes.text, "Yes.")
        XCTAssertEqual(QuickReply.no.text, "No.")
        XCTAssertEqual(QuickReply.wait.text, "Please wait a moment, I'm signing my reply.")
        XCTAssertEqual(QuickReply.repeat.text, "Sorry, could you please repeat that?")
    }

    func testQuickReplySetsDraftOnAFreshTurnWithoutSending() {
        store.add(.recognised(.hello))
        let sentBefore = sink.sent

        store.useQuickReply(.repeat)

        XCTAssertEqual(store.currentTurnID, turn(2))
        XCTAssertEqual(store.chips, [])
        XCTAssertEqual(store.draft, Draft(text: "Sorry, could you please repeat that?", origin: .quickReply))
        XCTAssertEqual(sink.sent, sentBefore, "a quick reply must wait for SEND")
    }

    func testSendingAQuickReplyApprovesItsTextOnTheFreshTurn() {
        store.useQuickReply(.yes)

        store.send()

        XCTAssertEqual(sink.sent, [.approve(turnID: turn(2), text: "Yes.")])
    }

    // MARK: Send

    func testSendApprovesExactlyTheShownDraft() {
        showDraft("Hello, I'd like a doctor's appointment tomorrow.")

        store.send()

        XCTAssertEqual(
            sink.sent.last,
            .approve(turnID: turn(1), text: "Hello, I'd like a doctor's appointment tomorrow."))
        XCTAssertEqual(
            store.sending,
            .speaking(turnID: turn(1), text: "Hello, I'd like a doctor's appointment tomorrow."))
    }

    func testSendWipesChipsAndDraftAndStartsANewTurn() {
        showDraft()
        store.add(.unsure())

        store.send()

        XCTAssertEqual(store.chips, [])
        XCTAssertNil(store.draft)
        XCTAssertEqual(store.currentTurnID, turn(2))
        store.add(.recognised(.yes))
        XCTAssertEqual(sink.sent.last, .chips(turnID: turn(2), chips: [.yes]))
    }

    func testDoubleSendApprovesOnce() {
        showDraft()

        store.send()
        store.send()

        XCTAssertEqual(sink.approvals.count, 1)
    }

    func testSendWithoutDraftSendsNothing() {
        store.add(.recognised(.hello))

        store.send()

        XCTAssertEqual(sink.approvals, [])
        XCTAssertEqual(store.sending, .idle)
    }

    func testSendBeforeTheCallConnectsSendsNothing() {
        let sink = FakeSink()
        let store = TurnStore(sink: sink, initialState: .ringing)
        store.useQuickReply(.yes)

        store.send()

        XCTAssertEqual(sink.sent, [])
        XCTAssertEqual(store.draft?.text, "Yes.", "the draft waits for the call")
    }

    func testSendWorksWhileTheAgentIsSpeaking() {
        store.receive(.status(.speaking))
        store.useQuickReply(.no)

        store.send()

        XCTAssertEqual(sink.approvals, [.approve(turnID: turn(2), text: "No.")])
    }

    func testSendIsBlockedWhileTheLastReplyIsStillBeingSpoken() {
        showDraft("Hello.")
        store.send()
        store.add(.recognised(.doctor))
        store.receive(.draft(turnID: turn(2), text: "I'd like to see a doctor.", source: .llm))

        XCTAssertFalse(store.canSend)
        store.send()

        XCTAssertEqual(sink.approvals, [.approve(turnID: turn(1), text: "Hello.")])
        XCTAssertEqual(store.draft?.text, "I'd like to see a doctor.", "the next reply waits")
    }

    func testNextReplyCanBeSentOnceTheLastIsConfirmed() {
        showDraft("Hello.")
        store.send()
        store.add(.recognised(.doctor))
        store.receive(.draft(turnID: turn(2), text: "I'd like to see a doctor.", source: .llm))

        store.receive(.spoken(turnID: turn(1)))
        store.send()

        XCTAssertEqual(sink.approvals.last, .approve(turnID: turn(2), text: "I'd like to see a doctor."))
    }

    func testDraftLongerThanTheBackendLimitIsNotSent() {
        let tooLong = String(repeating: "a", count: ProtocolLimits.maxSpokenCharacters + 1)
        showDraft(tooLong)

        store.send()

        XCTAssertFalse(store.canSend)
        XCTAssertEqual(sink.approvals, [])
    }

    func testDraftAtTheBackendLimitIsSent() {
        let atLimit = String(repeating: "a", count: ProtocolLimits.maxSpokenCharacters)
        showDraft(atLimit)

        store.send()

        XCTAssertEqual(sink.approvals, [.approve(turnID: turn(1), text: atLimit)])
    }

    func testLimitCountsUnicodeScalarsLikePython() {
        // 300 code points but 600 UTF-8 bytes: within the backend's limit.
        let accented = String(repeating: "\u{E9}", count: ProtocolLimits.maxSpokenCharacters)
        showDraft(accented)

        store.send()

        XCTAssertEqual(sink.approvals, [.approve(turnID: turn(1), text: accented)])
    }

    func testLimitDoesNotCountCombinedCharactersAsOne() {
        // 151 visible characters but 302 code points: over the backend's limit.
        let combining = String(repeating: "e\u{301}", count: 151)
        showDraft(combining)

        store.send()

        XCTAssertEqual(sink.approvals, [])
    }

    func testWhitespaceOnlyDraftIsNotSent() {
        showDraft(" \n ")

        store.send()

        XCTAssertFalse(store.canSend)
        XCTAssertEqual(sink.approvals, [])
    }

    func testEmptyDraftIsNotSent() {
        showDraft("")

        store.send()

        XCTAssertEqual(sink.approvals, [])
    }

    // MARK: Spoken and not delivered

    func testSpokenForTheSpeakingTurnMeansDelivered() {
        showDraft()
        store.send()

        store.receive(.spoken(turnID: turn(1)))

        XCTAssertEqual(store.sending, .delivered)
    }

    func testSpokenForAnotherTurnIsIgnored() {
        showDraft("Hello.")
        store.send()

        store.receive(.spoken(turnID: turn(2)))

        XCTAssertEqual(store.sending, .speaking(turnID: turn(1), text: "Hello."))
        XCTAssertEqual(store.captions, [])
    }

    func testSpokenReplyJoinsTheTranscriptAsTheUsersWords() {
        store.receive(.caption(text: "City Clinic, how can I help?", at: 1))
        showDraft("Hello.")
        store.send()

        store.receive(.spoken(turnID: turn(1)))

        XCTAssertEqual(store.captions.map(\.text), ["City Clinic, how can I help?", "Hello."])
        XCTAssertEqual(store.captions.map(\.speaker), [.receptionist, .user])
    }

    func testNotDeliveredReplyStaysOutOfTheTranscript() {
        showDraft("Hello.")
        store.send()

        store.receive(.notDelivered(turnID: turn(1), reason: "no_confirmation"))

        XCTAssertEqual(store.captions, [])
    }

    func testNotDeliveredOffersResendWithoutSendingAnything() {
        showDraft("Hello.")
        store.send()
        let sentBefore = sink.sent

        store.receive(.notDelivered(turnID: turn(1), reason: "no_confirmation"))

        XCTAssertEqual(store.sending, .notDelivered(text: "Hello."))
        XCTAssertEqual(sink.sent, sentBefore, "never resend automatically")
    }

    func testNotDeliveredForAnotherTurnIsIgnored() {
        showDraft("Hello.")
        store.send()

        store.receive(.notDelivered(turnID: turn(9), reason: "no_confirmation"))

        XCTAssertEqual(store.sending, .speaking(turnID: turn(1), text: "Hello."))
    }

    func testResendApprovesTheSameTextOnANewTurnID() {
        showDraft("Hello.")
        store.send()  // approves turn1; current turn becomes turn2
        store.receive(.notDelivered(turnID: turn(1), reason: "no_confirmation"))

        store.resend()

        XCTAssertEqual(
            sink.approvals,
            [.approve(turnID: turn(1), text: "Hello."), .approve(turnID: turn(3), text: "Hello.")])
        XCTAssertEqual(store.sending, .speaking(turnID: turn(3), text: "Hello."))
        XCTAssertEqual(store.currentTurnID, turn(4), "the next turn starts clean")
    }

    func testResendTwiceApprovesOnce() {
        showDraft("Hello.")
        store.send()
        store.receive(.notDelivered(turnID: turn(1), reason: "no_confirmation"))

        store.resend()
        store.resend()

        XCTAssertEqual(sink.approvals.count, 2)
    }

    func testCanResendOnlyAfterNotDeliveredWhileLive() {
        showDraft("Hello.")
        XCTAssertFalse(store.canResend)
        store.send()
        XCTAssertFalse(store.canResend)

        store.receive(.notDelivered(turnID: turn(1), reason: "no_confirmation"))
        XCTAssertTrue(store.canResend)

        store.receive(.status(.ringing))
        XCTAssertFalse(store.canResend)
    }

    func testResendDoesNothingUnlessNotDelivered() {
        showDraft("Hello.")
        store.resend()
        store.send()
        store.resend()
        store.receive(.spoken(turnID: turn(1)))
        store.resend()

        XCTAssertEqual(sink.approvals, [.approve(turnID: turn(1), text: "Hello.")])
    }

    func testResendWaitsWhileTheCallIsNotConnected() {
        showDraft("Hello.")
        store.send()
        store.receive(.notDelivered(turnID: turn(1), reason: "no_confirmation"))
        store.receive(.status(.ringing))

        store.resend()

        XCTAssertEqual(sink.approvals.count, 1)
        XCTAssertEqual(store.sending, .notDelivered(text: "Hello."))
    }

    func testResentTurnCanBeConfirmed() {
        showDraft("Hello.")
        store.send()
        store.receive(.notDelivered(turnID: turn(1), reason: "no_confirmation"))
        store.resend()

        store.receive(.spoken(turnID: turn(3)))

        XCTAssertEqual(store.sending, .delivered)
    }

    // MARK: Backend events

    func testStatusUpdatesState() {
        store.receive(.status(.speaking))
        XCTAssertEqual(store.state, .speaking)
        store.receive(.status(.inCall))
        XCTAssertEqual(store.state, .inCall)
    }

    func testConnectedAtIsSetOnceWhenTheCallFirstGoesLive() throws {
        let store = TurnStore(sink: FakeSink(), initialState: .dialing)
        store.receive(.status(.ringing))
        XCTAssertNil(store.connectedAt)

        store.receive(.status(.inCall))
        let connectedAt = try XCTUnwrap(store.connectedAt)
        store.receive(.status(.speaking))
        store.receive(.status(.inCall))

        XCTAssertEqual(store.connectedAt, connectedAt)
    }

    func testCaptionsAreKeptInOrder() {
        store.receive(.caption(text: "We have 4 pm tomorrow.", at: 100))
        store.receive(.caption(text: "Does that work?", at: 101.5))

        XCTAssertEqual(
            store.captions,
            [Caption(text: "We have 4 pm tomorrow.", at: Date(timeIntervalSince1970: 100)),
             Caption(text: "Does that work?", at: Date(timeIntervalSince1970: 101.5))])
    }

    func testAgentCaptionIsKeptAsTheAgentsLine() {
        store.receive(.caption(text: "Hello, I'm calling for a Deaf caller.", at: 1, speaker: .agent))
        store.receive(.caption(text: "City Clinic, how can I help?", at: 2, speaker: .receptionist))

        XCTAssertEqual(store.captions.map(\.speaker), [.agent, .receptionist])
    }

    func testAgentCaptionSendsNothingAndKeepsTheDraft() {
        showDraft("Hello.")
        let sentBefore = sink.sent

        store.receive(.caption(text: "One moment please, I'm signing my reply.", at: 1, speaker: .agent))

        XCTAssertEqual(sink.sent, sentBefore)
        XCTAssertEqual(store.draft?.text, "Hello.")
        XCTAssertEqual(store.sending, .idle)
    }

    func testCaptionKeepsTheDraft() {
        showDraft("Hello.")

        store.receive(.caption(text: "Hello?", at: 1))

        XCTAssertEqual(store.draft?.text, "Hello.")
    }

    func testBackendErrorIsRecordedWithoutChangingThePhase() {
        showDraft("Hello.")
        store.send()

        store.receive(.error(code: "stale_turn", message: "turn turn0 is not current"))

        XCTAssertEqual(store.lastError, ServerError(code: "stale_turn", message: "turn turn0 is not current"))
        XCTAssertEqual(store.sending, .speaking(turnID: turn(1), text: "Hello."))
    }

    func testUnknownMessageChangesNothing() {
        showDraft("Hello.")

        store.receive(.unknown(type: "future_thing"))

        XCTAssertEqual(store.draft?.text, "Hello.")
        XCTAssertEqual(store.state, .inCall)
    }

    // MARK: Stop and end

    func testStopSendsStopOnceWhileAReplyIsBeingSpoken() {
        store.useQuickReply(.yes)
        store.send()

        store.stop()
        store.stop()

        XCTAssertEqual(sink.sent.filter { $0 == .stop }.count, 1)
        XCTAssertTrue(store.isStopRequested)
    }

    func testStopDoesNothingWhenNoReplyIsBeingSpoken() {
        store.stop()

        XCTAssertEqual(sink.sent, [])
        XCTAssertFalse(store.isStopRequested)
    }

    func testStopCanBeSentAgainForTheNextReply() {
        store.useQuickReply(.yes)
        store.send()
        store.stop()
        store.receive(.notDelivered(turnID: turn(2), reason: "stopped"))
        XCTAssertFalse(store.isStopRequested)

        store.resend()
        store.stop()

        XCTAssertEqual(sink.sent.filter { $0 == .stop }.count, 2)
    }

    func testEndDropsPendingThenSendsEndAndWipesEverything() {
        store.receive(.caption(text: "Hello?", at: 1))
        showDraft("Hello.")
        store.add(.unsure())

        store.end()

        XCTAssertEqual(sink.log.suffix(2), ["discard", "send"])
        XCTAssertEqual(sink.sent.last, .end)
        XCTAssertEqual(store.state, .ended)
        XCTAssertEqual(store.chips, [])
        XCTAssertNil(store.draft)
        XCTAssertEqual(store.captions, [])
        XCTAssertEqual(store.sending, .idle)
    }

    func testEndWhileSpeakingClearsThePhase() {
        showDraft("Hello.")
        store.send()

        store.end()

        XCTAssertEqual(store.sending, .idle)
    }

    func testNothingIsSentAfterEnd() {
        showDraft("Hello.")
        store.end()
        let sentAtEnd = sink.sent

        XCTAssertFalse(store.add(.recognised(.yes)))
        store.useQuickReply(.yes)
        store.send()
        store.stop()
        store.clear()
        store.end()

        XCTAssertEqual(sink.sent, sentAtEnd)
        XCTAssertNil(store.draft)
    }

    func testBackendEventsAreIgnoredAfterEnd() {
        store.end()

        store.receive(.status(.inCall))
        store.receive(.caption(text: "Hello?", at: 1))
        store.receive(.draft(turnID: store.currentTurnID, text: "Hello.", source: .llm))
        store.connectionLost()

        XCTAssertEqual(store.state, .ended)
        XCTAssertEqual(store.captions, [])
        XCTAssertNil(store.draft)
        XCTAssertNil(store.notice)
    }

    func testBackendEndedStatusWipesWithoutSending() {
        showDraft("Hello.")
        let sentBefore = sink.sent

        store.receive(.status(.ended))

        XCTAssertEqual(store.state, .ended)
        XCTAssertNil(store.draft)
        XCTAssertEqual(store.chips, [])
        XCTAssertEqual(sink.sent, sentBefore)
        XCTAssertEqual(sink.log.last, "discard")
    }

    // MARK: Disconnect

    func testConnectionLostSaysNothingWillBeSentAndWipesDrafts() {
        showDraft("Hello.")
        store.add(.unsure())

        store.connectionLost()

        XCTAssertEqual(store.state, .error)
        XCTAssertEqual(store.notice, "Nothing will be sent")
        XCTAssertEqual(store.chips, [])
        XCTAssertNil(store.draft)
        XCTAssertEqual(sink.log.last, "discard")
    }

    func testConnectionLostWhileSpeakingDoesNotOfferResend() {
        showDraft("Hello.")
        store.send()

        store.connectionLost()
        store.resend()

        XCTAssertEqual(store.sending, .idle)
        XCTAssertEqual(sink.approvals.count, 1)
    }

    func testNothingIsSentWhileDisconnected() {
        store.connectionLost()
        let sentBefore = sink.sent

        XCTAssertFalse(store.add(.recognised(.yes)))
        store.useQuickReply(.yes)
        store.send()
        store.stop()

        XCTAssertEqual(sink.sent, sentBefore)
        XCTAssertNil(store.draft)
    }

    func testNoAutomaticResendAfterReconnect() {
        showDraft("Hello.")
        let sentBeforeDrop = sink.sent
        store.connectionLost()

        store.receive(.status(.inCall))

        XCTAssertEqual(sink.sent, sentBeforeDrop)
        XCTAssertNil(store.notice)
        XCTAssertEqual(store.state, .inCall)
        store.receive(.draft(turnID: turn(1), text: "Hello.", source: .llm))
        XCTAssertNil(store.draft, "the pre-disconnect turn is stale")
        store.add(.recognised(.yes))
        XCTAssertEqual(sink.sent.last, .chips(turnID: turn(2), chips: [.yes]))
    }

    func testBackendErrorStatusIsTreatedLikeADisconnect() {
        showDraft("Hello.")

        store.receive(.status(.error))
        store.send()

        XCTAssertEqual(store.state, .error)
        XCTAssertEqual(store.notice, TurnStore.disconnectedNotice)
        XCTAssertNil(store.draft)
        XCTAssertEqual(sink.approvals, [])
    }

    func testEndStillWorksAfterADisconnect() {
        store.connectionLost()

        store.end()

        XCTAssertEqual(sink.sent.last, .end)
        XCTAssertEqual(store.state, .ended)
        XCTAssertNil(store.notice)
    }

    func testConsumeAppliesEventsThenTreatsStreamEndAsDisconnect() async {
        let (events, continuation) = AsyncStream<ServerMessage>.makeStream()
        continuation.yield(.status(.speaking))
        continuation.yield(.caption(text: "Hi", at: 1))
        continuation.finish()

        await store.consume(events)

        XCTAssertEqual(store.captions.map(\.text), ["Hi"])
        XCTAssertEqual(store.state, .error)
        XCTAssertEqual(store.notice, TurnStore.disconnectedNotice)
    }

    func testCancelledConsumeIgnoresTheOldStreamAndReportsNoDisconnect() async {
        let (events, continuation) = AsyncStream<ServerMessage>.makeStream()
        continuation.yield(.status(.speaking))
        continuation.finish()
        let listener = Task { await store.consume(events) }

        listener.cancel()
        await listener.value

        XCTAssertEqual(store.state, .inCall)
        XCTAssertNil(store.notice)
    }

    func testCancelledConsumeOfAFinishedStreamReportsNoDisconnect() async {
        let (events, continuation) = AsyncStream<ServerMessage>.makeStream()
        continuation.finish()
        let listener = Task { await store.consume(events) }

        listener.cancel()
        await listener.value

        XCTAssertEqual(store.state, .inCall)
        XCTAssertNil(store.notice)
    }

    func testConsumeAfterBackendEndStaysEnded() async {
        let (events, continuation) = AsyncStream<ServerMessage>.makeStream()
        continuation.yield(.status(.ended))
        continuation.finish()

        await store.consume(events)

        XCTAssertEqual(store.state, .ended)
        XCTAssertNil(store.notice)
    }
}
