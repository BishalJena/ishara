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

    private func launch(_ arguments: [String]) {
        app = XCUIApplication()
        app.launchArguments = arguments
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

    private func openNotes(timeout: TimeInterval = 30) {
        let notes = app.buttons["call.notes"]
        XCTAssertTrue(notes.waitForExistence(timeout: timeout), "the call did not end with a notes button")
        notes.tap()
    }
}
