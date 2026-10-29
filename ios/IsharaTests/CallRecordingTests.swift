import CallSession
import XCTest
@testable import Ishara

/// What a finished call leaves in Recent calls, and how its late notes reach it.
@MainActor
final class CallRecordingTests: XCTestCase {
    private var folder: URL!

    override func setUp() async throws {
        folder = FileManager.default.temporaryDirectory.appending(path: "CallRecordingTests-\(UUID().uuidString)")
    }

    override func tearDown() async throws {
        try? FileManager.default.removeItem(at: folder)
    }

    private func placedCall(_ setup: CallSetup = .demo) async -> (ActiveCallViewModel, StubCallDriver) {
        let driver = StubCallDriver()
        let model = ActiveCallViewModel(setup: setup, driver: driver, recognition: StubRecognition())
        await model.start()
        driver.store.receive(.status(.inCall))
        return (model, driver)
    }

    func testACallIsRecordedOnlyOnceItIsOverWithItsCaptions() async throws {
        let (model, driver) = await placedCall()
        driver.store.receive(.caption(text: "We have 4 pm tomorrow.", at: 100, speaker: .receptionist))
        XCTAssertNil(model.record, "recorded while the call is still on")

        driver.store.receive(.status(.ended))

        let record = try XCTUnwrap(model.record)
        XCTAssertEqual(record.id, model.recordID)
        XCTAssertEqual(record.contactName, "City Clinic")
        XCTAssertEqual(record.mode, .live)
        XCTAssertNil(record.notes)
        XCTAssertEqual(record.captions.map(\.text), model.captions.map(\.text))
        XCTAssertTrue(record.captions.contains(
            CallRecord.Line(speaker: .receptionist, text: "We have 4 pm tomorrow.", at: Date(timeIntervalSince1970: 100))))
        XCTAssertEqual(model.record, record, "the same call gives the same record")
    }

    func testACallThatWasNeverPlacedIsNotRecorded() async {
        let driver = StubCallDriver()
        driver.startError = BackendError.httpStatus(403)
        let model = ActiveCallViewModel(setup: .demo, driver: driver, recognition: StubRecognition())
        await model.start()

        XCTAssertTrue(model.isCallOver)
        XCTAssertNil(model.record)
    }

    func testCaptionSpeakersAreKept() {
        let at = Date(timeIntervalSince1970: 5)
        let speakers = [Caption.Speaker.receptionist, .agent, .user].map { CallRecord.Line(Caption(text: "x", at: at, speaker: $0)).speaker }
        XCTAssertEqual(speakers, [.receptionist, .agent, .user])
    }

    /// The user's callback number goes into the brief request only; the saved call has the
    /// brief's words ("callback number"), never the number.
    func testASavedCallForMeHoldsNoPhoneNumber() async throws {
        let request = BriefRequest(
            purpose: .doctorAppointment, chips: [.tomorrow],
            profile: Profile(name: "Riya", callback: "+91 98765 43210", notes: "Fever since Monday"))
        let brief = DelegatedDemo.brief(for: request)
        var setup = CallSetup.demo
        setup.delegation = Delegation(brief: brief, attended: false)
        let (model, driver) = await placedCall(setup)
        driver.store.receive(.caption(text: DelegatedDemo.offer, at: 100, speaker: .receptionist))
        driver.store.receive(.status(.ended))
        let history = CallHistory(folder: folder)
        let record = try XCTUnwrap(model.record)
        history.save(record)
        history.update(record.id, notes: DelegatedDemo.notes(
            goal: brief.goal, name: "Riya", brief: brief.text,
            transcript: [TranscriptEntry(speaker: .receptionist, text: DelegatedDemo.offer, at: 100)],
            answers: [], ready: true))

        let json = try String(contentsOf: folder.appending(path: "\(record.id.uuidString).json"), encoding: .utf8)

        XCTAssertEqual(record.mode, .delegated)
        XCTAssertTrue(json.contains("May share: name (Riya), callback number."), "the brief wasn't saved")
        XCTAssertFalse(json.contains("98765"))
        XCTAssertFalse(json.contains("+91"))
    }

    // MARK: Follow-up after the call

    private func delegatedSetup() -> CallSetup {
        var setup = CallSetup.demo
        let request = BriefRequest(purpose: .doctorAppointment, chips: [.tomorrow], profile: Profile(name: "Riya"))
        setup.delegation = Delegation(brief: DelegatedDemo.brief(for: request), attended: false)
        return setup
    }

    private func delegatedNotes(bolna: String? = nil) -> CallNotes {
        CallNotes(callID: "c1", mode: .delegated, ready: true, outcome: "callback", bolnaSummary: bolna)
    }

    /// The user leaves at once (no notes screen at all); Bolna's summary comes two checks
    /// later and still reaches the saved call. Then the checking stops.
    func testCallForMeNotesAreFollowedAfterTheUserLeaves() async throws {
        let (model, driver) = await placedCall(delegatedSetup())
        driver.store.receive(.status(.ended))
        driver.notesResults = [.success(delegatedNotes()), .success(delegatedNotes()),
                               .success(delegatedNotes(bolna: "The caller will be called back."))]
        let history = CallHistory(folder: folder)

        let followed = CallFollowUp.callEnded(model, history: history, sleep: { _ in })
        model.leave()

        let saved = await eventually { CallHistory(folder: self.folder).records.first?.notes?.bolnaSummary != nil }
        XCTAssertTrue(saved, "Bolna's summary never reached the saved call")
        let record = try XCTUnwrap(CallHistory(folder: folder).records.first)
        XCTAssertEqual(record.id, model.recordID)
        XCTAssertEqual(record.notes?.bolnaSummary, "The caller will be called back.")
        XCTAssertEqual(record.notes?.outcome, "callback")
        try await Task.sleep(for: .milliseconds(100))
        XCTAssertEqual(driver.notesCalls, 3, "it kept checking after the summary was in")
        // The notes screen shows this same follow-up; opening it doesn't poll again.
        await followed?.start().value
        XCTAssertEqual(followed?.notes?.bolnaSummary, "The caller will be called back.")
        XCTAssertEqual(driver.notesCalls, 3)
    }

    func testTheFollowUpGivesUpWhenTheTriesRunOut() async throws {
        let (model, driver) = await placedCall(delegatedSetup())
        driver.store.receive(.status(.ended))
        driver.notesResults = [.success(delegatedNotes())]
        let history = CallHistory(folder: folder)

        _ = CallFollowUp.callEnded(model, history: history, sleep: { _ in })

        let gaveUp = await eventually { driver.notesCalls == NotesModel.maxRefreshes + 1 }
        XCTAssertTrue(gaveUp)
        try await Task.sleep(for: .milliseconds(100))
        XCTAssertEqual(driver.notesCalls, NotesModel.maxRefreshes + 1, "it went on past its tries")
        XCTAssertEqual(history.records.first?.notes, delegatedNotes(), "the notes it did get weren't saved")
    }

    /// A live call's notes never get an outcome or Bolna's summary, so nothing is followed.
    func testALiveCallIsSavedButNotFollowed() async throws {
        let (model, driver) = await placedCall()
        driver.store.receive(.status(.ended))
        driver.notesResults = [.success(CallNotes(callID: "c1", mode: .live, ready: true))]
        let history = CallHistory(folder: folder)

        XCTAssertNil(CallFollowUp.callEnded(model, history: history, sleep: { _ in }))

        XCTAssertEqual(history.records.map(\.id), [model.recordID])
        try await Task.sleep(for: .milliseconds(100))
        XCTAssertEqual(driver.notesCalls, 0)
    }

    func testACallThatWasNeverPlacedHasNoFollowUp() async {
        let driver = StubCallDriver()
        driver.startError = BackendError.httpStatus(403)
        let model = ActiveCallViewModel(setup: delegatedSetup(), driver: driver, recognition: StubRecognition())
        await model.start()
        let history = CallHistory(folder: folder)

        XCTAssertNil(CallFollowUp.callEnded(model, history: history, sleep: { _ in }))
        XCTAssertTrue(history.records.isEmpty)
        XCTAssertEqual(driver.notesCalls, 0)
    }

    func testTheNotesScreenHandsBolnasLateSummaryToTheSavedCall() async throws {
        let (model, driver) = await placedCall()
        driver.store.receive(.status(.ended))
        let history = CallHistory(folder: folder)
        let record = try XCTUnwrap(model.record)
        history.save(record)
        driver.notesResults = [
            .success(CallNotes(callID: "c1", mode: .delegated, ready: true, outcome: "callback")),
            .success(CallNotes(callID: "c1", mode: .delegated, ready: true, outcome: "callback", bolnaSummary: "Call back.")),
        ]
        let notes = NotesModel(contactName: "City Clinic", driver: driver,
                               onNotes: { history.update(record.id, notes: $0) }, sleep: { _ in })

        await notes.run()

        XCTAssertEqual(driver.notesCalls, 2)
        let saved = try XCTUnwrap(CallHistory(folder: folder).records.first)
        XCTAssertEqual(saved.notes?.bolnaSummary, "Call back.")
        XCTAssertEqual(saved.notes?.outcome, "callback")
        XCTAssertEqual(saved.captions, record.captions)
    }
}
