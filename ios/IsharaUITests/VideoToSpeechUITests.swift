import XCTest

/// Sign videos in, spoken sentences out: every call flow through the real app, the real
/// on-device recognition and the real backend, with nothing dialled and nothing paid.
///
///     saved clip ─▶ ClipFeed (the simulator's camera) ─▶ Holistic ─▶ detector ─▶ ASL model
///       ─▶ chip / ask answer ─▶ LiveCallDriver ─▶ backend (local_demo) ─▶ custom-LLM speak
///       response that the stand-in Bolna "voices" (`agent says:` in the server log)
///
/// Each test needs the local demo server with its own receptionist script, its stdout in a
/// file, the app built against it and a folder of clips named by sign. `scripts/e2e_video_to_speech.sh`
/// sets all of that up and runs each test against its own server; by hand:
///
///     # backend/: .venv/bin/python -m scripts.local_demo --port 8799 --receptionist offer > /tmp/e2e.log
///     # ios/Ishara/Config/Secrets.xcconfig: ISHARA_BACKEND_URL = http:/$()/127.0.0.1:8799,
///     #   ISHARA_APP_TOKEN = ishara-local-demo
///     TEST_RUNNER_ISHARA_LOCAL_BACKEND=1 TEST_RUNNER_ISHARA_LOCAL_BACKEND_LOG=/tmp/e2e.log \
///     TEST_RUNNER_ISHARA_E2E_CLIPS=<folder> xcodebuild … \
///       -only-testing:IsharaUITests/VideoToSpeechUITests/testAttendedCallForMeAnsweredBySignVideo test
///
/// The clip folder holds `rest.mov` (Get ready calibrates on it) and one clip per sign, named
/// `hello`, `no`, `tomorrow`, `please`, `yes`, `thankyou`, plus the negatives `none_oov` (an
/// ASL sign outside the vocabulary) and `none_rest` (hands never rise). Each must give its
/// result in the app (`RecognitionReplayUITests` checks the whole clip set).
@MainActor
final class VideoToSpeechUITests: XCTestCase {
    // backend/app/markers.py: the voice's fixed lines, said without a SEND.
    private let intro = "Hello, I'm calling for a Deaf caller who is using Ishara, a sign-language app. "
        + "Their replies may take a few seconds."
    private let goodbye = "Thank you for your time. Goodbye."
    // backend/app/templates.py for these chips and the doctor_appointment purpose.
    private let helloDraft = "Hello."
    private let noTomorrowPleaseDraft = "No, sorry, that doesn't work. Is there anything tomorrow? Please."
    private let yesThankYouDraft = "Yes, that works. Thank you."
    // backend/fakes/scripted_call.py RECEPTIONIST_SCRIPTS.
    private let clinicOffer = "We have 4 pm tomorrow. Does that work?"
    private let clinicCounter = "Yes, 10:30 tomorrow morning."
    private let openQuestion = "what time would you like to come in"
    private let offerInWords = "we have four pm tomorrow does that work"
    // backend/app/delegate.py: the rule brain's lines for the brief [tomorrow], profile Riya.
    private let opening = "I'd like to book a doctor's appointment for Riya, tomorrow."
    private let pauseLine = "One moment, please."
    private let callbackLine = "I'll need to check that and call back. Thank you."
    private let tomorrowAnswer = "Tomorrow, please. What times are available?"
    private let yesAnswer = "Yes, 4 pm tomorrow works. Thank you."

    private var app: XCUIApplication!
    private var log: LocalBackendLog!
    private var clips: String!
    private var timings: [(step: String, seconds: TimeInterval)] = []

    override func setUp() async throws {
        let environment = ProcessInfo.processInfo.environment
        try XCTSkipUnless(environment["ISHARA_LOCAL_BACKEND"] == "1",
                          "set TEST_RUNNER_ISHARA_LOCAL_BACKEND=1 once the local demo backend is up")
        let logPath = try XCTUnwrap(environment["ISHARA_LOCAL_BACKEND_LOG"],
                                    "set TEST_RUNNER_ISHARA_LOCAL_BACKEND_LOG to the server's stdout file")
        clips = try XCTUnwrap(environment["ISHARA_E2E_CLIPS"],
                              "set TEST_RUNNER_ISHARA_E2E_CLIPS to the folder of clips named by sign")
        log = LocalBackendLog(url: URL(fileURLWithPath: logPath))
        continueAfterFailure = false
    }

    override func tearDown() async throws {
        reportTimings()
    }

    // MARK: Live mode

    /// The PLAN §1 call signed from videos: HELLO; NO · (a rest stretch) · an unknown sign ·
    /// TOMORROW · PLEASE; YES · THANK-YOU. Each SEND speaks exactly the draft on screen, and
    /// nothing is spoken before it.
    func testLiveCallSignedFromVideosSpeaksExactlyEachApprovedDraft() throws {
        try requireReceptionist("clinic")
        launch()
        let before = log.spokenLines()
        app.startCall()
        expectSpoken([intro], after: before)
        app.waitFor(app.element("call.status"), labelContains: "In call")
        waitUntil("the detector to watch", timeout: 15) { self.app.cameraPillLabel.contains("Watching") }
        var spoken = before + [intro]

        // Turn 1
        sign("hello", chip: "hello")
        let turn1 = sendDraft(expecting: helloDraft, spokenSoFar: &spoken, label: "turn 1")
        app.waitFor(app.element("caption.receptionist"), labelContains: clinicOffer, timeout: 30)
        XCTAssertEqual(turn1, helloDraft)

        // Turn 2, with both negatives in the middle: a rest stretch adds nothing, an unknown
        // sign shows [?] and is never sent (the draft is the one for the three signs alone).
        sign("no", chip: "no")
        expectNoNewResult(from: "none_rest")
        sign("none_oov", chip: "unsure")
        sign("tomorrow", chip: "tomorrow")
        sign("please", chip: "please")
        app.keepScreenshot("e2e-live-turn2-chips", in: self)
        _ = sendDraft(expecting: noTomorrowPleaseDraft, spokenSoFar: &spoken, label: "turn 2")
        app.waitFor(app.element("caption.receptionist"), labelContains: clinicCounter, timeout: 30)

        // Turn 3
        sign("yes", chip: "yes")
        sign("thankyou", chip: "thankyou")
        _ = sendDraft(expecting: yesThankYouDraft, spokenSoFar: &spoken, label: "turn 3")

        app.buttons["call.end"].tap()
        app.waitFor(app.element("call.endedPanel"), labelContains: "You ended the call")
        XCTAssertFalse(app.buttons["call.send"].exists)
        expectSpoken([goodbye], after: spoken)
        app.keepScreenshot("e2e-live-ended", in: self)
    }

    // MARK: Call for me (D9)

    /// Attended: TOMORROW signed into the brief, the receptionist offers a time in words, and
    /// a signed YES answers the agent's question inside its 10 s window.
    func testAttendedCallForMeAnsweredBySignVideo() throws {
        try requireReceptionist("offer")
        let before = startCallForMe(attended: true)

        let ask = waitForAsk(offerInWords)
        XCTAssertTrue(app.buttons["ask.yes"].label.contains(yesAnswer), app.buttons["ask.yes"].label)
        expectSpoken([intro, opening, pauseLine], after: before)
        answerBySigning("yes", expecting: yesAnswer, askedAt: ask)
        expectSpoken([intro, opening, pauseLine, yesAnswer], after: before)

        expectNotes("Booked")
        XCTAssertFalse(log.spokenLines().contains(callbackLine), "the ask timed out into a callback")
    }

    /// Attended, version B: "what time would you like to come in" gets the time words; a
    /// signed TOMORROW is said for the user, then the offer in words gets a signed YES.
    func testOpenTimeQuestionAnsweredBySignVideos() throws {
        try requireReceptionist("open-question")
        let before = startCallForMe(attended: true)

        let timeAsk = waitForAsk(openQuestion)
        for choice in ["tomorrow", "morning", "now", "wait"] {
            XCTAssertTrue(app.buttons["ask.\(choice)"].exists, "no \(choice) answer")
        }
        XCTAssertFalse(app.buttons["ask.yes"].exists, "yes is no answer to \"what time?\"")
        app.keepScreenshot("e2e-open-question", in: self)
        answerBySigning("tomorrow", expecting: tomorrowAnswer, askedAt: timeAsk)
        expectSpoken([intro, opening, pauseLine, tomorrowAnswer], after: before)

        let offer = waitForAsk(offerInWords)
        answerBySigning("yes", expecting: yesAnswer, askedAt: offer)
        expectSpoken([intro, opening, pauseLine, tomorrowAnswer, pauseLine, yesAnswer], after: before)

        expectNotes("Booked")
        XCTAssertFalse(log.spokenLines().contains(callbackLine), "an ask timed out into a callback")
    }

    /// Unattended: the agent never asks; it promises a callback and the notes say so.
    func testUnattendedCallForMeComesBackAsACallback() throws {
        try requireReceptionist("offer")
        let before = startCallForMe(attended: false)

        expectNotes("The agent will need to call back")
        XCTAssertFalse(app.element("ask.question").exists, "an unattended call never asks")
        XCTAssertEqual(Array(log.spokenLines().dropFirst(before.count).prefix(3)), [intro, opening, callbackLine])
    }

    // MARK: Steps

    private func launch() {
        app = XCUIApplication()
        app.launchArguments = ["-IsharaDriver", "live", "-IsharaRecognition", "pipeline", "-IsharaSampleSigns", clips]
        app.launch()
    }

    /// The server log names the receptionist's script; each test needs its own.
    private func requireReceptionist(_ script: String) throws {
        let banner = log.text
        guard banner.contains("receptionist script: \(script)") else {
            throw XCTSkip("needs scripts.local_demo --receptionist \(script) (this server: "
                + "\(banner.split(separator: "\n").first { $0.contains("receptionist script") } ?? "no banner"))")
        }
    }

    /// Plays one clip as the camera and waits for its chip.
    private func sign(_ clip: String, chip: String, file: StaticString = #filePath, line: UInt = #line) {
        let start = Date()
        app.replay(clip, file: file, line: line)
        let tapped = Date()
        XCTAssertTrue(app.buttons["chip.\(chip)"].waitForExistence(timeout: 20),
                      "\(clip) gave no \(chip) chip", file: file, line: line)
        timings.append(("\(clip): menu tap → chip", Date().timeIntervalSince(tapped)))
        timings.append(("\(clip): open menu → chip", Date().timeIntervalSince(start)))
    }

    /// A clip that must add no result: no chip, no tile, nothing sent.
    private func expectNoNewResult(from clip: String, file: StaticString = #filePath, line: UInt = #line) {
        let chipsBefore = chipIdentifiers()
        app.replay(clip, file: file, line: line)
        _ = app.outcomes(timeout: 8)
        XCTAssertEqual(chipIdentifiers(), chipsBefore, "\(clip) added a result", file: file, line: line)
        XCTAssertFalse(app.buttons["candidate.accept"].exists, "\(clip) offered a pick-one", file: file, line: line)
    }

    private func chipIdentifiers() -> [String] {
        app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'chip.'")).allElementsBoundByIndex.map(\.identifier)
    }

    /// Waits for the backend's draft for the chips on screen, checks nothing was spoken
    /// meanwhile, taps SEND and expects the stand-in Bolna to speak exactly that draft.
    @discardableResult
    private func sendDraft(expecting expected: String, spokenSoFar spoken: inout [String], label: String,
                           file: StaticString = #filePath, line: UInt = #line) -> String {
        let chipsShown = Date()
        app.waitFor(app.element("call.draft"), labelContains: ": \(expected)", timeout: 20, file: file, line: line)
        timings.append(("\(label): last chip → draft", Date().timeIntervalSince(chipsShown)))
        let shown = draftText()
        XCTAssertEqual(shown, expected, "the draft on screen", file: file, line: line)
        XCTAssertFalse(app.element("caption.you").exists && app.element("caption.you").label.contains(shown),
                       "the draft was spoken before SEND", file: file, line: line)
        XCTAssertEqual(log.spokenLines(), spoken, "the backend spoke before SEND", file: file, line: line)
        app.keepScreenshot("e2e-\(label)-draft", in: self)

        let tapped = Date()
        app.sendAndExpectDelivered(shown, file: file, line: line)
        timings.append(("\(label): SEND → Delivered on screen", Date().timeIntervalSince(tapped)))
        expectSpoken([shown], after: spoken, file: file, line: line)
        timings.append(("\(label): SEND → spoken in the server log", Date().timeIntervalSince(tapped)))
        spoken.append(shown)
        return shown
    }

    /// "Draft from Template: Hello." → "Hello."
    private func draftText() -> String {
        let label = app.element("call.draft").label
        guard let colon = label.range(of: ": ") else { return label }
        return String(label[colon.upperBound...])
    }

    /// Home → Call for me → Get ready (calibrates on rest.mov) → TOMORROW signed into the
    /// brief → the brief → Approve and call. Returns what was spoken before the call.
    private func startCallForMe(attended: Bool) -> [String] {
        launch()
        let callForMe = app.buttons["home.callForMe"]
        XCTAssertTrue(callForMe.waitForExistence(timeout: 10))
        app.assertCallingNumberDisclosed()
        callForMe.tap()
        let start = app.buttons["getReady.start"]
        XCTAssertTrue(start.waitForExistence(timeout: 5))
        waitUntil("Get ready to calibrate on rest.mov", timeout: 30) { start.isEnabled }
        start.tap()
        XCTAssertTrue(app.buttons["brief.prepare"].waitForExistence(timeout: 10))

        sign("tomorrow", chip: "tomorrow")
        app.buttons["brief.prepare"].tap()
        app.waitFor(app.element("brief.text"), labelContains: "Preferred: tomorrow.")
        XCTAssertFalse(app.element("brief.text").label.contains("morning"), "the brief added a time nobody signed")
        app.assertCallingNumberDisclosed()
        if !attended { setAttended(false) }
        app.keepScreenshot("e2e-brief-\(attended ? "attended" : "unattended")", in: self)

        let before = log.spokenLines()
        let approve = app.buttons["brief.approve"]
        XCTAssertTrue(approve.waitForExistence(timeout: 5))
        approve.tap()
        return before
    }

    private func setAttended(_ attended: Bool) {
        let toggle = app.switches["brief.attended"]
        XCTAssertTrue(toggle.waitForExistence(timeout: 5))
        app.scrollViews.firstMatch.swipeUp()
        if (toggle.value as? String == "1") != attended {
            let control = toggle.switches.firstMatch
            (control.exists ? control : toggle).tap()
        }
        waitUntil("the attended switch to be \(attended)") { (toggle.value as? String == "1") == attended }
    }

    /// Waits for the agent's question to the user; returns when it showed.
    private func waitForAsk(_ question: String, file: StaticString = #filePath, line: UInt = #line) -> Date {
        app.waitFor(app.element("ask.question"), labelContains: question, timeout: 40, file: file, line: line)
        return Date()
    }

    /// Signs the answer from its clip while the question is open; the agent must say the
    /// option's sentence for the user.
    private func answerBySigning(_ clip: String, expecting sentence: String, askedAt: Date,
                                 file: StaticString = #filePath, line: UInt = #line) {
        revealReplayMenu(file: file, line: line)
        app.replay(clip, file: file, line: line)
        let tapped = Date()
        app.waitFor(app.element("caption.you"), labelContains: sentence, timeout: 15, file: file, line: line)
        let answered = Date().timeIntervalSince(askedAt)
        timings.append(("\(clip): clip picked → answer said", Date().timeIntervalSince(tapped)))
        timings.append(("\(clip): question shown → answer said (window 10 s)", answered))
        XCTAssertLessThan(answered, 10, "the signed answer came after the agent's 10 s question window",
                          file: file, line: line)
        app.keepScreenshot("e2e-answered-\(clip)", in: self)
    }

    /// The four-answer card of an open "when?" covers all but a strip of the camera card,
    /// with the simulator's replay menu just under its top edge (a tap there lands on the
    /// card). Scroll the camera card up into the strip above the card, as a user would.
    private func revealReplayMenu(file: StaticString = #filePath, line: UInt = #line) {
        let menu = app.buttons["replayMenu"]
        let panel = app.scrollViews.containing(.button, identifier: "replayMenu").firstMatch
        let header = app.staticTexts["The agent is asking you"]
        guard menu.exists, panel.exists, header.exists else { return }
        // The card's top edge: its padding and the bar's above the header.
        let cardTop = header.frame.minY - 32
        guard menu.frame.maxY > cardTop else { return }
        let lift = menu.frame.minY - (panel.frame.minY + 6)
        let start = panel.coordinate(withNormalizedOffset: .zero)
            .withOffset(CGVector(dx: 30, dy: min(cardTop, panel.frame.minY + 40) - panel.frame.minY - 4))
        start.press(forDuration: 0.1, thenDragTo: start.withOffset(CGVector(dx: 0, dy: -lift)),
                    withVelocity: .slow, thenHoldForDuration: 0.2)
        XCTAssertLessThanOrEqual(menu.frame.maxY, cardTop, "the replay menu is still under the ask card",
                                 file: file, line: line)
    }

    private func expectNotes(_ outcome: String, file: StaticString = #filePath, line: UInt = #line) {
        let notes = app.buttons["call.notes"]
        XCTAssertTrue(notes.waitForExistence(timeout: 45), "the call did not end with a notes button", file: file, line: line)
        notes.tap()
        // The outcome's icon shares its identifier, so read the text itself.
        app.waitFor(app.staticTexts["notes.outcome"], labelContains: outcome, timeout: 30, file: file, line: line)
        app.keepScreenshot("e2e-notes", in: self)
    }

    /// The server's spoken lines must be exactly `before + lines`, eventually.
    private func expectSpoken(_ lines: [String], after before: [String],
                              file: StaticString = #filePath, line: UInt = #line) {
        waitUntil("the backend to speak \(lines)", timeout: 30, file: file, line: line) {
            self.log.spokenLines() == before + lines
        }
        if log.spokenLines() != before + lines {
            XCTFail("spoken: \(log.spokenLines().dropFirst(before.count))", file: file, line: line)
        }
    }

    private func reportTimings() {
        guard !timings.isEmpty else { return }
        let table = timings.map { String(format: "%@ | %.2f s", $0.step, $0.seconds) }.joined(separator: "\n")
        print("e2e timings (\(name)):\n\(table)")
        let attachment = XCTAttachment(string: table)
        attachment.name = "e2e-timings"
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
