import XCTest

/// "Call for me" (decision D9) edge cases on the fake call: the brief is approved only as
/// shown, an answer speaks exactly the sentence on its button, an unanswered question falls
/// back to the callback line, and an unattended call never asks.
@MainActor
final class DelegatedEdgeCaseUITests: XCTestCase {
    private let briefWhen = "Preferred: tomorrow in the morning."
    // Call/DelegatedDemo.swift: the scripted offer and the agent's fallback.
    private let offer = "10:30 tomorrow morning"
    private let callbackLine = "I'll need to check that and call back. Thank you."

    private var app: XCUIApplication!

    override func setUp() async throws {
        continueAfterFailure = false
    }

    // MARK: Brief

    /// With signs on screen but no brief built yet, there is nothing to approve.
    func testBriefCanNotBeApprovedUntilPrepared() {
        launch(EdgeCaseLaunch.halfSpeed)
        openBrief()
        XCTAssertFalse(app.buttons["brief.approve"].exists, "Approve was offered before signing")

        app.buttons["brief.add.tomorrow"].tap()
        app.buttons["brief.add.morning"].tap()
        XCTAssertFalse(app.buttons["brief.approve"].exists, "Approve was offered before the brief was built")
        XCTAssertFalse(app.element("brief.text").exists)

        app.buttons["brief.prepare"].tap()
        app.waitFor(app.element("brief.text"), labelContains: briefWhen)
        XCTAssertTrue(app.buttons["brief.approve"].waitForExistence(timeout: 5))
    }

    /// Any edit after the brief was built (a removed sign, a changed name) hides it until it
    /// is built again; the attended choice is not part of the brief and keeps it.
    func testEditingAfterPreparingHidesTheBriefUntilRebuilt() {
        launch(EdgeCaseLaunch.halfSpeed)
        openBrief()
        prepare()

        setAttended(false)
        XCTAssertTrue(app.buttons["brief.approve"].exists, "the attended switch hid the brief")

        app.buttons["chip.morning"].tap()
        expectBriefHidden()
        prepare(expecting: "Preferred: tomorrow.")

        let name = app.textFields["brief.name"]
        name.tap()
        name.typeText(" K")
        expectBriefHidden()
        prepare(expecting: "Call on behalf of Riya K,")
    }

    // MARK: Attended questions

    /// The sentence on the tapped button is exactly what the agent says for the user.
    func testTappedAnswerSpeaksExactlyTheShownSentence() {
        launch(EdgeCaseLaunch.halfSpeed)
        openBrief()
        prepare()
        approve()

        app.waitFor(app.element("ask.question"), labelContains: offer)
        let no = app.buttons["ask.no"]
        let shown = spokenSentence(on: no)
        XCTAssertFalse(shown.isEmpty)
        no.tap()

        app.waitFor(app.element("caption.you"), labelContains: shown)
        XCTAssertFalse(app.element("ask.question").exists, "the question stayed open after the answer")
        openNotes()
        XCTAssertTrue(app.buttons["notes.done"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.scrolledToText(containing: "Agent (for you), \(shown)").exists,
                      "the notes transcript lacks the answer")
    }

    /// Nobody answers: the question stays up for its 10 s, then the agent says the
    /// fallback line and the card goes away. Runs at real speed to time the 10 s.
    func testUnansweredQuestionTimesOutAfterTenSecondsWithTheFallback() {
        launch([])
        openBrief()
        prepare()
        approve()

        app.waitFor(app.element("ask.question"), labelContains: offer)
        XCTAssertTrue(app.element("ask.question").exists)
        app.assertStays("the open question", for: 8) { app.buttons["ask.yes"].exists }
        waitUntil("the question to time out", timeout: 5) { !app.buttons["ask.yes"].exists }
        app.waitFor(app.element("caption.agent"), labelContains: callbackLine)
        XCTAssertFalse(app.element("caption.you").exists, "a timed-out question spoke an answer for the user")

        openNotes()
        app.waitFor(app.element("notes.outcome"), labelContains: "call back")
    }

    // MARK: Unattended

    /// The agent calls back instead of asking: no camera, no question card, at any point.
    func testUnattendedCallShowsNoCameraAndNoQuestion() {
        launch(EdgeCaseLaunch.halfSpeed)
        openBrief()
        prepare()
        setAttended(false)
        approve()

        XCTAssertTrue(app.element("call.delegatedNote").waitForExistence(timeout: 10))
        let notes = app.buttons["call.notes"]
        waitUntil("the unattended call to end", timeout: 30) {
            XCTAssertFalse(app.element("ask.question").exists, "an unattended call asked a question")
            XCTAssertFalse(app.element("camera.pill").exists, "an unattended call shows the camera")
            XCTAssertFalse(app.element("camera.preview").exists, "an unattended call shows the camera")
            return notes.exists
        }
        app.waitFor(app.element("caption.agent"), labelContains: callbackLine)
    }

    // MARK: Lost backend

    /// The backend goes away while the agent's question is open: the screen says so, the
    /// question can no longer be answered, and the Notes screen explains it can't load
    /// them, on every Refresh, without crashing or showing stale notes.
    func testBackendGoingAwayDuringTheCallAndOnTheNotes() {
        launch(EdgeCaseLaunch.halfSpeed + ["-IsharaFakeConnectionDrop", "staysDown"])
        openBrief()
        prepare()
        approve()
        app.waitFor(app.element("ask.question"), labelContains: offer)

        XCTAssertTrue(app.element("call.connectionLostPanel").waitForExistence(timeout: 10))
        XCTAssertFalse(app.buttons["ask.yes"].exists, "a question was still offered with the connection gone")
        let notes = app.buttons["call.notes"]
        XCTAssertTrue(notes.waitForExistence(timeout: 10), "no way to the notes once the connection is gone")
        notes.tap()

        let failure = app.staticTexts.containing(NSPredicate(format: "label CONTAINS 'notes couldn' AND label CONTAINS 'be loaded'"))
        XCTAssertTrue(failure.firstMatch.waitForExistence(timeout: 10), "Notes didn't say why they are missing")
        XCTAssertFalse(app.element("notes.outcome").exists)
        let refresh = app.buttons["notes.refresh"]
        XCTAssertTrue(refresh.waitForExistence(timeout: 5))
        waitUntil("Refresh to be enabled") { refresh.isEnabled }
        refresh.tap()
        waitUntil("Refresh to finish") { refresh.isEnabled }
        XCTAssertTrue(failure.firstMatch.exists, "Refresh lost the explanation")
        app.buttons["notes.done"].tap()
        XCTAssertTrue(app.buttons["home.callForMe"].waitForExistence(timeout: 10))
    }

    /// The same through the real backend (`backend/scripts/local_demo.py`), stopped while
    /// the agent's question is open. Opt-in like
    /// `CallEdgeCaseUITests.testBackendStoppedMidCallThroughTheLocalBackend`.
    func testBackendStoppedDuringTheCallThroughTheLocalBackend() throws {
        let pid = try localBackendPID()
        launch(["-IsharaDriver", "live", "-IsharaRecognition", "scripted"])
        openBrief()
        prepare()
        approve()
        // backend/fakes/scripted_call.py: the receptionist's first line, handed to the user.
        app.waitFor(app.element("ask.question"), labelContains: "We have 4 pm tomorrow", timeout: 30)

        XCTAssertEqual(kill(pid, SIGTERM), 0, "couldn't stop the local backend (pid \(pid))")

        XCTAssertTrue(app.element("call.connectionLostPanel").waitForExistence(timeout: 15))
        XCTAssertFalse(app.buttons["ask.yes"].exists, "a question was still offered with the connection gone")
        let notes = app.buttons["call.notes"]
        XCTAssertTrue(notes.waitForExistence(timeout: 60), "no way to the notes once the connection is gone")
        notes.tap()
        let failure = app.staticTexts.containing(NSPredicate(format: "label CONTAINS 'notes couldn' AND label CONTAINS 'be loaded'"))
        XCTAssertTrue(failure.firstMatch.waitForExistence(timeout: 30), "Notes didn't say why they are missing")
        let refresh = app.buttons["notes.refresh"]
        waitUntil("Refresh to be enabled", timeout: 30) { refresh.isEnabled }
        refresh.tap()
        waitUntil("Refresh to finish", timeout: 30) { refresh.isEnabled }
        XCTAssertTrue(failure.firstMatch.exists, "Refresh lost the explanation")
    }

    // MARK: Notes

    /// The call service's summary is marked as possibly wrong, and the transcript (what was
    /// actually said) is shown with it.
    func testNotesMarkTheAutomaticSummaryAsFallibleAndShowTheTranscript() {
        launch(EdgeCaseLaunch.fixture("notes"))
        app.waitFor(app.element("notes.outcome"), labelContains: "Booked")
        XCTAssertTrue(app.scrolledToText(containing: "They said, Great, you're booked for 10:30 tomorrow morning.").exists,
                      "the transcript is missing")
        XCTAssertTrue(app.scrolledToText(containing: "The caller booked a doctor's appointment").exists)
        XCTAssertTrue(app.scrolledToText(containing: "It can be wrong; the transcript is what was said.").exists,
                      "the automatic summary isn't marked as possibly wrong")
    }

    // MARK: Everywhere

    /// Every button on the Call for me screens has a spoken name.
    func testEveryButtonHasAnAccessibilityLabel() {
        launch(EdgeCaseLaunch.halfSpeed)
        openBrief()
        app.assertEveryButtonLabelled(on: "Brief")
        prepare()
        app.assertEveryButtonLabelled(on: "Brief, prepared")
        approve()
        app.waitFor(app.element("ask.question"), labelContains: offer)
        app.assertEveryButtonLabelled(on: "Delegated call, asking")
        app.buttons["ask.yes"].tap()
        openNotes()
        XCTAssertTrue(app.buttons["notes.done"].waitForExistence(timeout: 10))
        app.assertEveryButtonLabelled(on: "Notes")
    }

    /// At the largest text size, Approve and call and the yes / no / wait answers stay on
    /// screen and tappable. Double-length timers keep the question open while checking.
    func testCriticalButtonsStayReachableAtTheLargestTextSize() {
        launch(EdgeCaseLaunch.largestText + ["-IsharaFakeTimeScale", "2"])
        openBrief()
        prepare()
        app.assertReachable(app.buttons["brief.approve"], "Approve and call")
        app.keepScreenshot("delegated-brief-largest-text", in: self)
        approve()

        XCTAssertTrue(app.element("ask.question").waitForExistence(timeout: 30))
        for choice in ["yes", "no", "wait"] {
            app.assertReachable(app.buttons["ask.\(choice)"], choice)
        }
        app.assertReachable(app.buttons["call.end"], "End")
        app.keepScreenshot("delegated-ask-largest-text", in: self)
        app.buttons["ask.wait"].tap()
        XCTAssertTrue(app.element("ask.question").exists, "wait closed the question")
    }

    /// Screenshots of the Call for me screens, kept in the results. Opt-in like
    /// `CallEdgeCaseUITests.testScreenshotsOfEveryScreen`.
    func testScreenshotsOfEveryScreen() throws {
        let mode = try screenshotMode()
        launch(["-IsharaFakeTimeScale", "2"])
        openBrief()
        app.keepScreenshot("delegated-brief-\(mode)", in: self)
        prepare()
        app.keepScreenshot("delegated-brief-prepared-\(mode)", in: self)
        approve()
        XCTAssertTrue(app.element("ask.question").waitForExistence(timeout: 30))
        app.keepScreenshot("delegated-ask-\(mode)", in: self)
        app.buttons["ask.yes"].tap()
        openNotes(timeout: 40)
        XCTAssertTrue(app.buttons["notes.done"].waitForExistence(timeout: 10))
        Thread.sleep(forTimeInterval: 1)
        app.keepScreenshot("delegated-notes-\(mode)", in: self)
    }

    // MARK: Steps

    private func launch(_ arguments: [String]) {
        app = XCUIApplication()
        app.launchArguments = arguments
        app.launch()
    }

    /// Home → Get ready → Brief, checking the calling-number note on all three.
    private func openBrief() {
        let callForMe = app.buttons["home.callForMe"]
        XCTAssertTrue(callForMe.waitForExistence(timeout: 10))
        app.assertCallingNumberDisclosed()
        callForMe.tap()

        let start = app.buttons["getReady.start"]
        XCTAssertTrue(start.waitForExistence(timeout: 5))
        app.assertCallingNumberDisclosed()
        waitUntil("Get ready to finish its checks") { start.isEnabled }
        start.tap()

        XCTAssertTrue(app.buttons["brief.prepare"].waitForExistence(timeout: 5))
        app.assertCallingNumberDisclosed()
    }

    /// Taps tomorrow and morning (when not on screen yet), then builds the brief.
    private func prepare(expecting text: String? = nil) {
        for sign in ["tomorrow", "morning"] where !app.buttons["chip.\(sign)"].exists && text == nil {
            app.buttons["brief.add.\(sign)"].tap()
        }
        app.buttons["brief.prepare"].tap()
        app.waitFor(app.element("brief.text"), labelContains: text ?? briefWhen)
        XCTAssertTrue(app.buttons["brief.approve"].waitForExistence(timeout: 5))
    }

    private func expectBriefHidden(file: StaticString = #filePath, line: UInt = #line) {
        waitUntil("the brief to be hidden", timeout: 5, file: file, line: line) {
            !app.buttons["brief.approve"].exists && !app.element("brief.text").exists
        }
        XCTAssertTrue(app.buttons["brief.prepare"].exists, file: file, line: line)
    }

    private func setAttended(_ attended: Bool) {
        let toggle = app.switches["brief.attended"]
        XCTAssertTrue(toggle.waitForExistence(timeout: 5))
        if !toggle.isHittable { app.scrollViews.firstMatch.swipeUp() }
        if (toggle.value as? String == "1") != attended {
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

    /// An answer button reads "YES, <sentence>": the sentence is what the agent will say.
    private func spokenSentence(on button: XCUIElement) -> String {
        let label = button.label
        guard let comma = label.firstIndex(of: ",") else { return label }
        return label[label.index(after: comma)...].trimmingCharacters(in: .whitespaces)
    }
}
