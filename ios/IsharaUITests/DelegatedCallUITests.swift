import XCTest

/// "Call for me" (decision D9) through the real screens: Home → Get ready → sign or tap the
/// request → read the brief → approve it once → the agent's call → the notes.
///
/// The demo-mode tests run on the fake call. The local-backend test runs the real backend
/// code against its scripted receptionist (`backend/scripts/local_demo.py`), set up exactly
/// as for `LocalBackendCallUITests`; nothing is dialled.
@MainActor
final class DelegatedCallUITests: XCTestCase {
    private var app: XCUIApplication!

    override func setUp() async throws {
        continueAfterFailure = false
    }

    // MARK: Demo mode (fake call)

    func testAttendedCallForMeAsksThenBooks() {
        launch(["-IsharaFakeTimeScale", "0.5"])
        prepareBrief(expecting: "Preferred: tomorrow in the morning.")
        approve()

        XCTAssertTrue(app.element("call.delegatedNote").waitForExistence(timeout: 10))
        XCTAssertFalse(app.buttons["call.send"].exists, "a delegated call has no SEND")
        app.waitFor(app.element("ask.question"), labelContains: "10:30 tomorrow morning")
        app.buttons["ask.yes"].tap()

        openNotes()
        app.waitFor(app.element("notes.outcome"), labelContains: "Booked")
        app.buttons["notes.done"].tap()
        XCTAssertTrue(app.buttons["home.callForMe"].waitForExistence(timeout: 10))
    }

    /// Version B: the receptionist asks "when?" with no time on offer. The fake call signs
    /// TOMORROW through the scripted recognizer: the agent says its sentence for the user,
    /// the receptionist then offers a time, and YES books it.
    func testOpenTimeQuestionAnsweredBySigningTomorrowThenYesBooks() {
        launch(["-IsharaFakeTimeScale", "0.5", "-IsharaFakeOpenQuestion", "tomorrow"])
        prepareBrief(expecting: "Preferred: tomorrow in the morning.")
        approve()

        app.waitFor(app.element("ask.question"), labelContains: "What time would you like")
        app.waitFor(app.element("caption.you"), labelContains: "Tomorrow, please. What times are available?")
        app.waitFor(app.element("ask.question"), labelContains: "10:30 tomorrow morning")
        app.buttons["ask.yes"].tap()

        openNotes()
        app.waitFor(app.element("notes.outcome"), labelContains: "Booked")
    }

    /// Version B by tap: the card offers the time words and WAIT, each with the exact
    /// sentence the agent will say; MORNING speaks exactly its own.
    func testOpenTimeQuestionTappedMorningSpeaksExactlyItsSentence() {
        launch(["-IsharaFakeOpenQuestion", "tap"])
        prepareBrief(expecting: "Preferred: tomorrow in the morning.")
        approve()

        app.waitFor(app.element("ask.question"), labelContains: "What time would you like")
        for choice in ["tomorrow", "morning", "now", "wait"] {
            XCTAssertTrue(app.buttons["ask.\(choice)"].exists, "no \(choice) answer")
        }
        XCTAssertFalse(app.buttons["ask.yes"].exists, "yes is no answer to \"what time?\"")
        let morning = app.buttons["ask.morning"]
        XCTAssertTrue(morning.label.contains("In the morning, please. What times are available?"), morning.label)
        app.keepScreenshot("delegated-time-ask", in: self)
        morning.tap()

        app.waitFor(app.element("caption.you"), labelContains: "In the morning, please. What times are available?")
        app.waitFor(app.element("ask.question"), labelContains: "10:30 tomorrow morning")
        app.buttons["ask.yes"].tap()
        openNotes()
        app.waitFor(app.element("notes.outcome"), labelContains: "Booked")
    }

    func testUnattendedCallForMeComesBackAsAQuestion() {
        launch(["-IsharaFakeTimeScale", "0.5"])
        prepareBrief(expecting: "Preferred: tomorrow in the morning.")
        setAttended(false)
        approve()

        openNotes()
        app.waitFor(app.element("notes.outcome"), labelContains: "call back")
        XCTAssertFalse(app.element("ask.question").exists, "an unattended call never asks")
    }

    /// Bolna's summary lands a while after the call ended (its final webhook). The notes
    /// screen, opened before that, picks it up by itself: nobody taps Refresh.
    func testNotesPickUpBolnasLateSummaryWithoutARefresh() {
        launch(["-IsharaFakeTimeScale", "0.5", "-IsharaFakeBolnaSummary", "24"])
        prepareBrief(expecting: "Preferred: tomorrow in the morning.")
        setAttended(false)
        approve()

        openNotes()
        app.waitFor(app.element("notes.outcome"), labelContains: "call back")
        let summary = app.element("notes.bolnaSummary")
        // At the end of the transcript, where the summary goes once it's in.
        XCTAssertTrue(app.scrolledToText(containing: "Agent (for you), I'll need to check that and call back.").exists)
        XCTAssertFalse(summary.exists, "the summary was there before Bolna sent it")

        XCTAssertTrue(app.swipedUntilExists(summary, timeout: 30), "Bolna's summary never reached the notes")
        app.waitFor(summary, labelContains: "The agent called to book a doctor's appointment for Riya.", timeout: 1)
    }

    // MARK: Recent calls

    /// Done right away, long before Bolna's summary: the app goes on checking the notes, and
    /// the summary reaches the saved call in Recent calls (whose screen only reads it). Its
    /// row opens the same notes, read only, and a swipe deletes it.
    func testACallForMeStaysInRecentCallsWithItsLateSummaryUntilDeleted() {
        launch(["-IsharaFakeTimeScale", "0.5", "-IsharaFakeBolnaSummary", "24"])
        XCTAssertFalse(app.buttons["recentCalls.row"].exists, "a call from an earlier run is on Home")
        callForMeUnattended()
        openNotes()
        app.waitFor(app.element("notes.outcome"), labelContains: "call back")
        app.buttons["notes.done"].tap()

        let row = app.recentCallRow()
        XCTAssertTrue(row.label.contains("City Clinic"), row.label)
        XCTAssertTrue(row.label.contains("The agent will need to call back"), row.label)
        app.keepScreenshot("recent-calls", in: self)
        row.tap()
        app.waitFor(app.element("notes.outcome"), labelContains: "call back")
        app.keepScreenshot("recent-call-detail", in: self)
        XCTAssertFalse(app.buttons["notes.refresh"].exists, "a saved call is read only")
        XCTAssertTrue(app.scrolledToText(containing: "Agent (for you), I'll need to check that and call back.").exists,
                      "the transcript is missing")
        let summary = app.element("notes.bolnaSummary")
        XCTAssertFalse(summary.exists, "the summary was there before Bolna sent it")
        XCTAssertTrue(app.swipedUntilExists(summary, timeout: 30), "Bolna's summary never reached the saved call")
        app.waitFor(summary, labelContains: "The agent called to book a doctor's appointment for Riya.", timeout: 1)
        app.keepScreenshot("recent-call-summary", in: self)
        app.navigationBars.buttons["Ishara"].tap()

        // Opened again, the saved call has it.
        app.recentCallRow().tap()
        XCTAssertTrue(app.swipedUntilExists(app.element("notes.bolnaSummary"), timeout: 5))
        app.navigationBars.buttons["Ishara"].tap()

        app.recentCallRow().swipeLeft()
        app.buttons["Delete"].tap()
        waitUntil("the deleted call to leave Home") { !app.buttons["recentCalls.row"].exists }
    }

    /// The call is saved on the phone, with notes loaded although the notes screen was never
    /// opened: the app quits and opens again with it on Home.
    func testRecentCallsSurviveARelaunch() throws {
        let folder = FileManager.default.temporaryDirectory.appending(path: "ishara-history-\(UUID().uuidString)")
        addTeardownBlock { try? FileManager.default.removeItem(at: folder) }
        let arguments = ["-IsharaFakeTimeScale", "0.5"]
        launch(arguments, history: ["-IsharaCallHistory", folder.path])
        callForMeUnattended()
        XCTAssertTrue(app.buttons["call.backHome"].waitForExistence(timeout: 30))
        app.buttons["call.backHome"].tap()
        let firstRow = app.recentCallRow()
        XCTAssertTrue(firstRow.label.contains("City Clinic"), firstRow.label)
        waitUntil("the notes to reach the saved call without the notes screen", timeout: 15) {
            app.buttons.matching(identifier: "recentCalls.row").firstMatch.label.contains("The agent will need to call back")
        }

        app.terminate()
        launch(arguments, history: ["-IsharaCallHistory", folder.path])

        let row = app.recentCallRow()
        XCTAssertTrue(row.label.contains("City Clinic"), row.label)
        XCTAssertTrue(row.label.contains("The agent will need to call back"), row.label)
        XCTAssertEqual(app.buttons.matching(identifier: "recentCalls.row").count, 1)
    }

    func testEditingTheRequestHidesTheBriefUntilRebuilt() {
        launch(["-IsharaFakeTimeScale", "0.5"])
        prepareBrief(expecting: "Preferred: tomorrow in the morning.")
        app.buttons["brief.add.evening"].tap()

        XCTAssertFalse(app.buttons["brief.approve"].exists, "the shown brief no longer matches the request")
        XCTAssertTrue(app.buttons["brief.prepare"].waitForExistence(timeout: 5))
    }

    // MARK: Local backend

    func testCallForMeThroughTheLocalBackend() throws {
        try XCTSkipUnless(ProcessInfo.processInfo.environment["ISHARA_LOCAL_BACKEND"] == "1",
                          "set TEST_RUNNER_ISHARA_LOCAL_BACKEND=1 once the local demo backend is up")
        launch(["-IsharaDriver", "live", "-IsharaRecognition", "scripted"])
        // backend/app/delegate.py build_brief, for these chips and the demo profile.
        prepareBrief(expecting: "Call on behalf of Riya, who is Deaf and uses the Ishara app, "
            + "to book a doctor's appointment. Preferred: tomorrow in the morning.")
        approve()

        // backend/fakes/scripted_call.py: the receptionist's first line, handed to the user.
        app.waitFor(app.element("ask.question"), labelContains: "We have 4 pm tomorrow", timeout: 30)
        app.buttons["ask.yes"].tap()
        app.waitFor(app.element("caption.you"), labelContains: "Yes, 4 pm tomorrow works.")

        openNotes(timeout: 40)
        app.waitFor(app.element("notes.outcome"), labelContains: "Booked")
    }

    // MARK: Steps

    private func launch(_ arguments: [String], history: [String] = EdgeCaseLaunch.freshHistory) {
        app = XCUIApplication()
        app.launchArguments = history + arguments
        app.launch()
    }

    /// Home → Get ready → Brief, taps tomorrow and morning, builds the brief.
    private func prepareBrief(expecting text: String) {
        let callForMe = app.buttons["home.callForMe"]
        XCTAssertTrue(callForMe.waitForExistence(timeout: 10))
        app.assertCallingNumberDisclosed()
        callForMe.tap()

        let start = app.buttons["getReady.start"]
        XCTAssertTrue(start.waitForExistence(timeout: 5))
        waitUntil("Get ready to finish its checks") { start.isEnabled }
        start.tap()

        XCTAssertTrue(app.buttons["brief.add.tomorrow"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["brief.approve"].exists, "nothing to approve before the brief is built")
        app.buttons["brief.add.tomorrow"].tap()
        app.buttons["brief.add.morning"].tap()
        XCTAssertTrue(app.buttons["chip.tomorrow"].exists)
        app.buttons["brief.prepare"].tap()
        app.waitFor(app.element("brief.text"), labelContains: text)
        app.assertCallingNumberDisclosed()
    }

    private func setAttended(_ attended: Bool) {
        let toggle = app.switches["brief.attended"]
        XCTAssertTrue(toggle.waitForExistence(timeout: 5))
        // The switch sits below the brief, under the bottom bar until scrolled up.
        app.scrollViews.firstMatch.swipeUp()
        if (toggle.value as? String == "1") != attended {
            // Tapping the label does nothing on iOS; tap the switch control itself.
            let control = toggle.switches.firstMatch
            (control.exists ? control : toggle).tap()
        }
        waitUntil("the attended switch to be \(attended)") { (toggle.value as? String == "1") == attended }
    }

    private func approve() {
        let approve = app.buttons["brief.approve"]
        XCTAssertTrue(approve.waitForExistence(timeout: 5))
        approve.tap()
    }

    private func callForMeUnattended() {
        prepareBrief(expecting: "Preferred: tomorrow in the morning.")
        setAttended(false)
        approve()
    }

    private func openNotes(timeout: TimeInterval = 30) {
        let notes = app.buttons["call.notes"]
        XCTAssertTrue(notes.waitForExistence(timeout: timeout), "the call did not end with a notes button")
        notes.tap()
    }
}
