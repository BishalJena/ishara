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

    /// The brief is built below the request and the details; the user must see it before
    /// Approve, not find it hidden under the bar that holds the button.
    func testPreparedBriefScrollsIntoViewAboveApprove() {
        launch(EdgeCaseLaunch.halfSpeed)
        openBrief()
        prepare()
        waitUntil("the brief to be in view above Approve", timeout: 3) {
            app.isInView("brief.text", above: "brief.actionBar")
        }
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

    // MARK: Camera above the question (issue #88)

    /// The receptionist's question as the live transcriber wrote it on the 28 Oct real call.
    private let realTranscript = "what time would will would you like to come in"
    private let longerTranscript = "sorry about the wait so what time would will would you like to come in "
        + "tomorrow or would the morning or later on in the afternoon suit her better do you think"

    /// The user signs the answer, so the camera stays in view above the four time answers,
    /// with the question worded as the real call's transcript.
    func testCameraStaysInViewAboveTheTimeQuestionAsTranscribed() {
        expectCameraInViewAboveTimeQuestion(realTranscript)
    }

    /// However long the transcribed question, the card doesn't grow over the camera.
    func testCameraStaysInViewAboveALongerTimeQuestion() {
        expectCameraInViewAboveTimeQuestion(longerTranscript)
    }

    /// The same at XL text, the largest size whose answer buttons hold their sentences.
    func testCameraStaysInViewAboveALongerTimeQuestionAtXLText() {
        expectCameraInViewAboveTimeQuestion(longerTranscript, textSize: EdgeCaseLaunch.textSize("XL"))
    }

    /// And at the largest size below the accessibility sizes, where the sentences scroll
    /// in the card above short answer buttons.
    func testCameraStaysInViewAboveALongerTimeQuestionAtTheLargestStandardTextSize() {
        expectCameraInViewAboveTimeQuestion(longerTranscript, textSize: EdgeCaseLaunch.textSize("XXXL"))
    }

    /// The yes / no / wait card too.
    func testCameraStaysInViewAboveTheYesNoQuestion() {
        launch(["-IsharaFakeTimeScale", "2"])
        openBrief()
        prepare()
        approve()
        app.waitFor(app.element("ask.question"), labelContains: offer, timeout: 30)
        app.assertCameraInViewAboveActionBar()
        expectAnswers(["yes": "Yes, 10:30 tomorrow works. Thank you.",
                       "no": "No, 10:30 tomorrow doesn't work, sorry. Is there another time?",
                       "wait": waitSentence])
        app.keepScreenshot("delegated-ask-camera", in: self)
    }

    // Call/DelegatedDemo.swift: the open "when?" answers.
    private let waitSentence = "One moment, please, I'm checking."
    private var timeAnswers: [String: String] {
        ["tomorrow": "Tomorrow, please. What times are available?",
         "morning": "In the morning, please. What times are available?",
         "now": "Today, as soon as possible, please. What times are available?",
         "wait": waitSentence]
    }

    /// Each answer is a big enough target, wholly on screen, and its exact sentence is on
    /// the card (on the button, or in the card's scrolling sentences at large sizes).
    private func expectAnswers(_ sentences: [String: String], file: StaticString = #filePath, line: UInt = #line) {
        for (choice, sentence) in sentences {
            let button = app.buttons["ask.\(choice)"]
            app.assertReachable(button, choice, file: file, line: line)
            XCTAssertGreaterThanOrEqual(button.frame.height, 44, "\(choice) is too small to tap", file: file, line: line)
            XCTAssertGreaterThanOrEqual(button.frame.width, 44, "\(choice) is too small to tap", file: file, line: line)
            let shown = app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", sentence))
            XCTAssertGreaterThan(shown.count, 0, "\(choice)'s sentence \u{201C}\(sentence)\u{201D} isn't on the card",
                                 file: file, line: line)
        }
    }

    private func expectCameraInViewAboveTimeQuestion(_ question: String, textSize: [String] = [],
                                                     file: StaticString = #filePath, line: UInt = #line) {
        launch(textSize + ["-IsharaFakeTimeScale", "2", "-IsharaFakeOpenQuestion", "tap",
                           "-IsharaFakeOpenQuestionText", question])
        openBrief()
        prepare()
        approve()
        // The card may show the question in short; VoiceOver still reads all of it.
        app.waitFor(app.element("ask.question"), labelContains: question, timeout: 30, file: file, line: line)
        app.assertCameraInViewAboveActionBar(file: file, line: line)
        expectAnswers(timeAnswers, file: file, line: line)
        app.assertReachable(app.buttons["call.end"], "End", file: file, line: line)
        app.keepScreenshot("delegated-time-ask-camera", in: self)
        app.buttons["ask.tomorrow"].tap()
        app.waitFor(app.element("caption.you"), labelContains: "Tomorrow, please.", file: file, line: line)
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

    /// The open "when?" card's four answers (TOMORROW is the longest word) also stay on
    /// screen and tappable at the largest text size, with a long transcribed question.
    func testTimeWordAnswersStayReachableAtTheLargestTextSize() {
        launch(EdgeCaseLaunch.largestText + ["-IsharaFakeTimeScale", "2", "-IsharaFakeOpenQuestion", "tap",
                                             "-IsharaFakeOpenQuestionText", longerTranscript])
        openBrief()
        prepare()
        approve()

        app.waitFor(app.element("ask.question"), labelContains: longerTranscript, timeout: 30)
        for choice in ["tomorrow", "morning", "now", "wait"] {
            app.assertReachable(app.buttons["ask.\(choice)"], choice)
        }
        app.assertReachable(app.buttons["call.end"], "End")
        app.keepScreenshot("delegated-time-ask-largest-text", in: self)
        app.buttons["ask.tomorrow"].tap()
        app.waitFor(app.element("caption.you"), labelContains: "Tomorrow, please.")
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
        app.launchArguments = EdgeCaseLaunch.freshHistory + arguments
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
