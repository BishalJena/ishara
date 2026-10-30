import XCTest

@testable import CallSession

/// Steer calls: proposals in the filling Send bar, presence, stepping in by typing, and
/// the wire shapes both ways.
@MainActor
final class SteerTests: XCTestCase {
    private var sink: FakeSink!
    private var store: TurnStore!

    override func setUp() async throws {
        sink = FakeSink()
        store = TurnStore(sink: sink, initialState: .inCall)
    }

    private func propose(_ text: String = "Yes, 10:30 Wednesday works.", origin: ProposalOrigin = .agent) {
        store.receive(.proposal(turnID: TurnID("steer-1")!, text: text, windowS: 4, origin: origin))
    }

    func testAProposalShowsUntilItsWindowIsResolved() {
        propose()
        XCTAssertEqual(store.proposal?.text, "Yes, 10:30 Wednesday works.")
        XCTAssertEqual(store.proposal?.origin, .agent)
        store.receive(.proposalResolved(turnID: TurnID("steer-1")!, outcome: .spoken))
        XCTAssertNil(store.proposal)
    }

    func testProgressFollowsTheWindow() {
        let shown = Date()
        let proposal = Proposal(turnID: TurnID("t")!, text: "x", windowS: 4, origin: .agent, shownAt: shown)
        XCTAssertEqual(proposal.progress(at: shown), 0)
        XCTAssertEqual(proposal.progress(at: shown.addingTimeInterval(2)), 0.5)
        XCTAssertEqual(proposal.progress(at: shown.addingTimeInterval(9)), 1)
    }

    func testSendNowApprovesTheProposedLineOnItsTurn() {
        propose()
        store.approveProposal()
        XCTAssertEqual(sink.sent, [.approve(turnID: TurnID("steer-1")!, text: "Yes, 10:30 Wednesday works.")])
        XCTAssertNil(store.proposal)
    }

    func testStartingToComposeHoldsTheAgentsLine() {
        propose()
        store.startComposing()
        XCTAssertTrue(store.isComposing)
        XCTAssertNil(store.proposal, "the dropped line leaves the bar")
        XCTAssertEqual(sink.sent, [.hold(turnID: TurnID("steer-1")!, composing: true)])
        store.startComposing()
        XCTAssertEqual(sink.sent.count, 1, "hold is sent once per composing spell")
    }

    func testBackingOutReleasesTheHold() {
        propose()
        store.startComposing()
        store.stopComposing()
        XCTAssertFalse(store.isComposing)
        XCTAssertEqual(sink.sent.last, .hold(turnID: store.currentTurnID, composing: false))
    }

    func testSayingALineSendsItTrimmedAndCountsAStepIn() {
        store.startComposing()
        XCTAssertTrue(store.say("  can we do 11 instead  "))
        XCTAssertEqual(sink.sent.last, .say(text: "can we do 11 instead"))
        XCTAssertFalse(store.isComposing)
        XCTAssertEqual(store.steppedIn, 1)
        XCTAssertFalse(store.say("   "), "nothing to say")
        XCTAssertFalse(store.say(String(repeating: "a", count: 301)), "over the spoken limit")
    }

    func testAPreviewedTypedLineCanBeHeldForEditing() {
        propose("Could we make it 11 instead?", origin: .user)
        store.holdPreview()
        XCTAssertEqual(sink.sent, [.hold(turnID: TurnID("steer-1")!, composing: true)])
        XCTAssertTrue(store.isComposing)
        XCTAssertNil(store.proposal)
    }

    func testHoldPreviewIgnoresAgentProposals() {
        propose()
        store.holdPreview()
        XCTAssertTrue(sink.sent.isEmpty)
        XCTAssertNotNil(store.proposal)
    }

    func testLookingAwayIsReportedAndDropsTheAgentsProposal() {
        propose()
        store.setPresent(false)
        XCTAssertEqual(sink.sent, [.presence(present: false)])
        XCTAssertNil(store.proposal, "the backend speaks it now")
        store.setPresent(true)
        XCTAssertEqual(sink.sent.last, .presence(present: true))
    }

    func testFollowUpsAccumulate() {
        store.receive(.followUp(text: "And his insurance number?"))
        store.receive(.followUp(text: "His address?"))
        XCTAssertEqual(store.followUps, ["And his insurance number?", "His address?"])
    }

    func testNothingSteersAfterTheCallEnded() {
        propose()
        store.receive(.status(.ended))
        store.approveProposal()
        store.setPresent(true)
        XCTAssertFalse(store.say("hello"))
        XCTAssertEqual(sink.sent.filter { if case .end = $0 { false } else { true } }, [])
    }

    // MARK: Wire

    func testAppMessagesEncodeAsTheBackendExpects() throws {
        XCTAssertEqual(try WireCoding.encodeText(.presence(present: true)), #"{"present":true,"type":"presence"}"#)
        XCTAssertEqual(
            try WireCoding.encodeText(.hold(turnID: TurnID("steer-1")!, composing: true)),
            #"{"composing":true,"turn_id":"steer-1","type":"hold"}"#)
        XCTAssertEqual(try WireCoding.encodeText(.say(text: "can we do 11")), #"{"text":"can we do 11","type":"say"}"#)
    }

    func testServerMessagesDecode() throws {
        let proposal = try WireCoding.decodeServerMessage(
            #"{"type":"proposal","turn_id":"steer-1","text":"Yes.","window_s":3.75,"origin":"user"}"#)
        XCTAssertEqual(proposal, .proposal(turnID: TurnID("steer-1")!, text: "Yes.", windowS: 3.75, origin: .user))
        let resolved = try WireCoding.decodeServerMessage(
            #"{"type":"proposal_resolved","turn_id":"steer-1","outcome":"held"}"#)
        XCTAssertEqual(resolved, .proposalResolved(turnID: TurnID("steer-1")!, outcome: .held))
        XCTAssertEqual(
            try WireCoding.decodeServerMessage(#"{"type":"follow_up","text":"DOB?"}"#), .followUp(text: "DOB?"))
    }

    func testStartRequestCarriesAPhoneNumberInsteadOfAContact() throws {
        let request = StartCallRequest(phoneNumber: "+910000000001", purpose: .doctorAppointment, mode: .steer, briefID: "b1")
        let json = String(decoding: try WireCoding.makeEncoder().encode(request), as: UTF8.self)
        XCTAssertTrue(json.contains(#""phone_number":"+910000000001""#))
        XCTAssertTrue(json.contains(#""mode":"steer""#))
        XCTAssertFalse(json.contains(#""contact_id":""#))
    }

    func testBriefRequestCarriesTheTypedRequestAndDetails() throws {
        let request = BriefRequest(
            purpose: .doctorAppointment, chips: [],
            profile: Profile(name: "Bishal", details: [Detail(label: "Date of birth", value: "12 March 1998")]),
            request: "Book a check-up next week, mornings only.")
        let json = String(decoding: try WireCoding.makeEncoder().encode(request), as: UTF8.self)
        XCTAssertTrue(json.contains(#""request":"Book a check-up next week, mornings only.""#))
        XCTAssertTrue(json.contains(#""details":[{"label":"Date of birth","value":"12 March 1998"}]"#))
    }

    func testNotesDecodeWithAndWithoutTheSteerFields() throws {
        let old = #"{"call_id":"c","mode":"delegated","ready":true,"summary":[],"open_questions":[],"transcript":[]}"#
        let notes = try JSONDecoder().decode(CallNotes.self, from: Data(old.utf8))
        XCTAssertEqual(notes.followUps, [])
        XCTAssertEqual(notes.steppedIn, 0)
        let new = #"{"call_id":"c","mode":"steer","ready":true,"follow_ups":["DOB?"],"stepped_in":2}"#
        let steer = try JSONDecoder().decode(CallNotes.self, from: Data(new.utf8))
        XCTAssertEqual(steer.mode, .steer)
        XCTAssertEqual(steer.followUps, ["DOB?"])
        XCTAssertEqual(steer.steppedIn, 2)
    }
}
