import CallSession
import XCTest
@testable import Ishara

@MainActor
final class BriefModelTests: XCTestCase {
    private var driver: StubCallDriver!
    private var model: BriefModel!

    override func setUp() async throws {
        driver = StubCallDriver()
        model = BriefModel(setup: .demo, driver: driver, recognition: StubRecognition())
    }

    func testLegacyBriefPreservesTheEntireSuppliedContext() {
        var setup = CallSetup.demo
        setup.request = "Book a check-up."
        setup.callback = "callback fixture"
        setup.sharedDetails = [Detail(label: "Patient ID", value: "DEMO-104")]
        setup.documents = [Document(name: "Report.pdf", text: "Allergies: none reported.")]
        let model = BriefModel(setup: setup, driver: driver, recognition: StubRecognition())
        XCTAssertEqual(model.request.request, setup.request)
        XCTAssertEqual(model.request.profile.callback, setup.callback)
        XCTAssertEqual(model.request.profile.details, setup.sharedDetails)
        XCTAssertEqual(model.request.profile.documents, setup.documents)
    }

    func testSignsBecomeChipsOnceEach() {
        model.handle(.result(.sign(.tomorrow)))
        model.handle(.result(.sign(.morning)))
        model.handle(.result(.sign(.tomorrow)))

        XCTAssertEqual(model.chips, [.tomorrow, .morning])
    }

    func testUnsureAndFramingAreExplainedNotAdded() {
        model.handle(.result(.unsure))
        XCTAssertTrue(model.lastSignUnsure)
        XCTAssertFalse(model.showsFramingHint)

        model.handle(.result(.handLeftFrame))
        XCTAssertTrue(model.showsFramingHint)
        XCTAssertTrue(model.chips.isEmpty)

        model.add(.today)
        XCTAssertFalse(model.lastSignUnsure)
    }

    func testCandidateNeedsATap() {
        model.handle(.result(.candidate(.tomorrow)))
        XCTAssertTrue(model.chips.isEmpty)

        model.acceptCandidate()
        XCTAssertEqual(model.chips, [.tomorrow])
        XCTAssertNil(model.candidate)
    }

    func testBriefIsBuiltFromExactlyWhatIsOnScreen() async {
        model.add(.tomorrow)
        model.callback = " +91 98 "
        model.reason = ""

        await model.prepare()

        XCTAssertEqual(driver.briefRequests, [BriefRequest(
            purpose: .doctorAppointment, chips: [.tomorrow], profile: Profile(name: "Riya", callback: "+91 98"))])
        XCTAssertEqual(model.brief?.briefID, "b1")
    }

    func testEditingAfterTheBriefHidesItUntilRebuilt() async {
        model.add(.tomorrow)
        await model.prepare()
        XCTAssertNotNil(model.approvedSetup)

        model.add(.morning)

        XCTAssertNil(model.brief, "the shown brief no longer matches the chips")
        XCTAssertNil(model.approvedSetup)
        model.remove(.morning)
        XCTAssertNotNil(model.brief, "back to what was approved")
    }

    func testApprovedSetupCarriesTheBriefAndTheChoice() async {
        model.name = "  Asha "
        await model.prepare()
        model.attended = false

        let approved = try? XCTUnwrap(model.approvedSetup)

        XCTAssertEqual(approved?.details.name, "Asha")
        XCTAssertEqual(approved?.delegation, Delegation(brief: driver.briefResult.value!, attended: false))
        XCTAssertEqual(approved?.contact, .cityClinic)
    }

    func testNoNameNoBrief() async {
        model.name = "   "

        XCTAssertFalse(model.canPrepare)
        await model.prepare()
        XCTAssertTrue(driver.briefRequests.isEmpty)
    }

    func testBackendRefusalIsExplained() async {
        driver.briefResult = .failure(BackendError.httpStatus(422))

        await model.prepare()

        XCTAssertNil(model.brief)
        XCTAssertEqual(model.failure, "The backend didn't accept these details. Check the name and callback number.")
    }
}

@MainActor
final class NotesModelTests: XCTestCase {
    private func notes(ready: Bool, bolna: String? = nil, presented: Bool = false) -> CallNotes {
        CallNotes(callID: "c1", mode: .delegated, ready: ready, outcome: ready ? "booked" : nil, bolnaSummary: bolna,
                  presentation: presented
                    ? CallPresentation(title: "Book a check-up", overview: "The appointment was booked.") : nil)
    }

    func testKeepsCheckingUntilTheCallEndedAndPresentationIsReady() async {
        let driver = StubCallDriver()
        driver.notesResults = [.success(notes(ready: false)), .success(notes(ready: true)),
                               .success(notes(ready: true, bolna: "Booked for 10:30.", presented: true))]
        let model = NotesModel(contactName: "City Clinic", driver: driver, sleep: { _ in })

        await model.run()

        XCTAssertEqual(driver.notesCalls, 3)
        XCTAssertEqual(model.notes?.bolnaSummary, "Booked for 10:30.")
        XCTAssertTrue(model.isComplete)
    }

    func testBlankSummaryKeepsPollingAndMissingSummaryStopsShowingAsPending() async {
        let driver = StubCallDriver()
        driver.notesResults = [.success(notes(ready: true, bolna: " \n")),
                               .success(notes(ready: true, bolna: "Booked for 10:30.", presented: true))]
        let model = NotesModel(contactName: "City Clinic", driver: driver, sleep: { _ in })
        await model.run()
        XCTAssertEqual(driver.notesCalls, 2)
        XCTAssertEqual(model.notes?.automaticSummary, "Booked for 10:30.")
        XCTAssertFalse(model.awaitingSummary)
        let unavailable = NotesModel(contactName: "City Clinic", driver: StubCallDriver(), sleep: { _ in throw CancellationError() })
        await unavailable.run()
        XCTAssertFalse(unavailable.awaitingSummary, "The screen must not promise a summary after polling stops")
    }

    func testStopsAfterTheLastRefreshWithoutReadyPresentation() async {
        let driver = StubCallDriver()
        driver.notesResults = [.success(notes(ready: true))]
        let model = NotesModel(contactName: "City Clinic", driver: driver, sleep: { _ in })

        await model.run()

        XCTAssertEqual(driver.notesCalls, NotesModel.maxRefreshes + 1)
        XCTAssertEqual(model.notes?.outcome, "booked")
    }

    func testStartPollsOnceHoweverOftenItIsAskedTo() async {
        let driver = StubCallDriver()
        driver.notesResults = [.success(notes(ready: true)), .success(notes(ready: true, bolna: "Booked for 10:30.", presented: true))]
        let model = NotesModel(contactName: "City Clinic", driver: driver, sleep: { _ in })

        let first = model.start()
        let second = model.start()
        await first.value
        await second.value
        await model.start().value

        XCTAssertEqual(driver.notesCalls, 2, "a second loop polled the same call")
        XCTAssertTrue(model.isComplete)
    }

    func testStopEndsThePolling() async {
        let driver = StubCallDriver()
        driver.notesResults = [.success(notes(ready: true))]
        let model = NotesModel(contactName: "City Clinic", driver: driver)  // real 3 s waits

        let polling = model.start()
        let loaded = await eventually { driver.notesCalls == 1 }
        XCTAssertTrue(loaded)
        model.stop()
        await polling.value

        XCTAssertEqual(driver.notesCalls, 1)
    }

    func testAForgottenCallIsExplained() async {
        let driver = StubCallDriver()
        driver.notesResults = [.failure(BackendError.httpStatus(404))]
        let model = NotesModel(contactName: "City Clinic", driver: driver, sleep: { _ in throw CancellationError() })

        await model.run()

        XCTAssertEqual(model.failure, "The backend no longer has this call (it may have restarted).")
    }

    func testProviderSummaryDoesNotCompletePendingPresentation() async {
        let driver = StubCallDriver()
        var pending = notes(ready: true, bolna: "A long upstream narrative.", presented: true)
        pending.presentation?.status = "pending"
        var ready = pending
        ready.presentation?.status = "ready"
        driver.notesResults = [.success(pending), .success(ready)]
        let model = NotesModel(contactName: "City Clinic", driver: driver, sleep: { _ in })
        await model.run()
        XCTAssertEqual(driver.notesCalls, 2)
        XCTAssertTrue(model.isComplete)
    }

    func testLegacyGeneralBriefUsesRequestClauseWithoutSplittingDoctorAbbreviation() {
        let brief = "Call on behalf of Asha, who uses the Ishara app, to carry out their approved request. "
            + "Request: Book an appointment with Dr. Rao. Preferred: tomorrow morning. "
            + "Reason, if asked: a routine check-up. May share: supplied report. Will not agree to unrelated requests."
        XCTAssertEqual(CallNotes.requestTitle(brief), "Book an appointment with Dr. Rao")
        for context in ["Preferred: tomorrow.", "Reason, if asked: a check-up.", "May share: supplied report.", "Will not agree to unrelated requests."] {
            let brief = "Call on behalf of Asha, to carry out their approved request. Request: Book an appointment with Dr. Rao. " + context
            XCTAssertEqual(CallNotes.requestTitle(brief), "Book an appointment with Dr. Rao")
        }
        let notes = CallNotes(callID: "legacy", mode: .steer, ready: true, brief: brief, outcome: "callback")
        XCTAssertEqual(notes.summaryTitle, "Book an appointment with Dr. Rao")
    }

    func testOutcomeWords() {
        XCTAssertEqual(NotesModel.describe(outcome: "booked", ready: true), "Booked")
        XCTAssertEqual(NotesModel.describe(outcome: "callback", ready: true), "Follow-up needed")
        XCTAssertEqual(NotesModel.describe(outcome: nil, ready: false), "The call is still being wrapped up")
        XCTAssertEqual(NotesModel.describe(outcome: "unclear", ready: true), "Outcome not confirmed")
    }
}

private extension Result {
    var value: Success? { try? get() }
}
