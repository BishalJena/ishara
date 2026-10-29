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
/// **A real call** (`TEST_RUNNER_ISHARA_E2E_BACKEND=deployed`, set by
/// `scripts/e2e_video_to_speech.sh --real`): the same flows through the deployed backend and
/// real Bolna, with a person answering the phone. There is no server log to read, so the
/// screen is the evidence: each SEND reaches Delivered and becomes the user's caption, the
/// signed answer becomes the user's caption inside the 10 s window, the receptionist's
/// words show as captions and the notes give the outcome. The LLM may word a draft
/// differently from the template (a template draft must still match exactly), and the
/// receptionist's captions are Deepgram's transcript, matched by key words. The person is
/// told what to say and when through `HumanReceptionist`. `--rehearse` runs this mode
/// against the local server, for free.
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
    // Word for word the 28 Oct real call's transcript (issue #88).
    private let openQuestion = "what time would will would you like to come in"
    private let offerInWords = "we have four pm tomorrow does that work"
    // backend/app/delegate.py: the rule brain's lines for the brief [tomorrow], profile Riya.
    private let opening = "I'd like to book a doctor's appointment for Riya, tomorrow."
    private let pauseLine = "One moment, please."
    private let callbackLine = "I'll need to check that and call back. Thank you."
    private let tomorrowAnswer = "Tomorrow, please. What times are available?"
    private let yesAnswer = "Yes, 4 pm tomorrow works. Thank you."

    /// Where the test hears what the agent said.
    private enum Backend {
        /// `scripts.local_demo`: its stand-in Bolna logs every line it voices.
        case local(LocalBackendLog)
        /// The deployed backend and real Bolna: a person answers, the screen is the evidence.
        case deployed(HumanReceptionist)
    }

    private var app: XCUIApplication!
    private var backend: Backend!
    private var clips: String!
    private var timings: [(step: String, seconds: TimeInterval)] = []

    private var log: LocalBackendLog? {
        if case .local(let log) = backend { return log }
        return nil
    }

    private var human: HumanReceptionist? {
        if case .deployed(let human) = backend { return human }
        return nil
    }

    /// A real call: the deployed backend, not `--rehearse` against the local stand-in, which
    /// sends no summary.
    private var callsRealBolna: Bool {
        human != nil && ProcessInfo.processInfo.environment["ISHARA_LOCAL_BACKEND"] != "1"
    }

    override func setUp() async throws {
        let environment = ProcessInfo.processInfo.environment
        if environment["ISHARA_E2E_BACKEND"] == "deployed" {
            backend = .deployed(try HumanReceptionist(environment: environment))
        } else {
            try XCTSkipUnless(environment["ISHARA_LOCAL_BACKEND"] == "1",
                              "set TEST_RUNNER_ISHARA_LOCAL_BACKEND=1 once the local demo backend is up")
            let logPath = try XCTUnwrap(environment["ISHARA_LOCAL_BACKEND_LOG"],
                                        "set TEST_RUNNER_ISHARA_LOCAL_BACKEND_LOG to the server's stdout file")
            backend = .local(LocalBackendLog(url: URL(fileURLWithPath: logPath)))
        }
        clips = try XCTUnwrap(environment["ISHARA_E2E_CLIPS"],
                              "set TEST_RUNNER_ISHARA_E2E_CLIPS to the folder of clips named by sign")
        continueAfterFailure = false
    }

    override func tearDown() async throws {
        reportTimings()
        guard let human else { return }
        // A failed step must not leave a paid call open.
        let end = app?.buttons["call.end"]
        if let end, end.exists, end.isHittable { end.tap() }
        // `hasSucceeded` is only final after tearDown; the failure count so far is.
        let failed = (testRun?.failureCount ?? 0) + (testRun?.unexpectedExceptionCount ?? 0) > 0
        human.tell("FINISHED: \(failed ? "FAILED" : "passed"). Hang up if the call is still on.")
    }

    // MARK: Live mode

    /// The PLAN §1 call signed from videos: HELLO; NO · (a rest stretch) · an unknown sign ·
    /// TOMORROW · PLEASE; YES · THANK-YOU. Each SEND speaks exactly the draft on screen, and
    /// nothing is spoken before it.
    func testLiveCallSignedFromVideosSpeaksExactlyEachApprovedDraft() throws {
        try requireReceptionist("clinic")
        launch()
        let before = spokenLines()
        app.startCall()
        waitUntilAnswered()
        expectSpoken([intro], after: before)
        app.waitFor(app.element("call.status"), labelContains: "In call")
        waitUntil("the detector to watch", timeout: 15) { self.app.cameraPillLabel.contains("Watching") }
        var spoken = before + [intro]

        // Turn 1
        sign("hello", chip: "hello")
        var heard = receptionistCaption()
        let turn1 = sendDraft(expecting: helloDraft, mentioning: [], spokenSoFar: &spoken, label: "turn 1")
        hearReceptionist(0, scripted: clinicOffer, keywords: ["4", "four", "tomorrow", "work"],
                         after: heard, once: turn1)

        // Turn 2, with both negatives in the middle: a rest stretch adds nothing, an unknown
        // sign shows [?] and is never sent (the draft is the one for the three signs alone).
        human?.tell("Stay quiet: the user signs NO, a rest, an unknown sign, TOMORROW, PLEASE "
            + "(about 30 s; you may hear “One moment please, I'm signing my reply.”).")
        sign("no", chip: "no")
        expectNoNewResult(from: "none_rest")
        sign("none_oov", chip: "unsure")
        sign("tomorrow", chip: "tomorrow")
        sign("please", chip: "please")
        app.keepScreenshot("e2e-live-turn2-chips", in: self)
        heard = receptionistCaption()
        let turn2 = sendDraft(expecting: noTomorrowPleaseDraft, mentioning: ["tomorrow"],
                              spokenSoFar: &spoken, label: "turn 2")
        hearReceptionist(1, scripted: clinicCounter, keywords: ["10", "ten", "morning", "tomorrow"],
                         after: heard, once: turn2)

        // Turn 3
        human?.tell("Stay quiet: the user signs YES, THANK-YOU.")
        sign("yes", chip: "yes")
        sign("thankyou", chip: "thankyou")
        let turn3 = sendDraft(expecting: yesThankYouDraft, mentioning: ["thank"], spokenSoFar: &spoken, label: "turn 3")

        human?.tell("Stay quiet: once the voice has said “\(turn3)” the app ends the call "
            + "(you hear “\(goodbye)”).")
        // Real speech takes a few seconds; End would cut the last reply off.
        if human != nil { Thread.sleep(forTimeInterval: 6) }
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

        sayAfterOpening(0)
        let ask = waitForAsk(offerInWords, answer: "yes")
        let yes = offeredYes()
        expectSpoken([intro, opening, pauseLine], after: before)
        answerBySigning("yes", expecting: yes, askedAt: ask)
        expectSpoken([intro, opening, pauseLine, yes], after: before)

        human?.tell("Stay quiet: the agent hangs up by itself in about 10 s.")
        expectNotes("Booked")
        XCTAssertFalse(spokenLines().contains(callbackLine), "the ask timed out into a callback")
    }

    /// Attended, version B: "what time would will would you like to come in" gets the time
    /// words, with the camera and its replay menu still in view above them; a signed TOMORROW
    /// is said for the user, then the offer in words gets a signed YES.
    func testOpenTimeQuestionAnsweredBySignVideos() throws {
        try requireReceptionist("open-question")
        let before = startCallForMe(attended: true)

        sayAfterOpening(0)
        let timeAsk = waitForAsk(openQuestion, answer: "tomorrow")
        for choice in ["tomorrow", "morning", "now", "wait"] {
            XCTAssertTrue(app.buttons["ask.\(choice)"].exists, "no \(choice) answer")
        }
        XCTAssertFalse(app.buttons["ask.yes"].exists, "yes is no answer to \"what time?\"")
        app.assertCameraInViewAboveActionBar()
        app.keepScreenshot("e2e-open-question", in: self)
        answerBySigning("tomorrow", expecting: tomorrowAnswer, askedAt: timeAsk)
        expectSpoken([intro, opening, pauseLine, tomorrowAnswer], after: before)

        if let human {
            human.tell("SAY NOW (once the agent has said “\(tomorrowAnswer)”): “\(human.line(1))”")
        }
        let offer = waitForAsk(offerInWords, answer: "yes")
        let yes = offeredYes()
        answerBySigning("yes", expecting: yes, askedAt: offer)
        expectSpoken([intro, opening, pauseLine, tomorrowAnswer, pauseLine, yes], after: before)

        human?.tell("Stay quiet: the agent hangs up by itself in about 10 s.")
        expectNotes("Booked")
        XCTAssertFalse(spokenLines().contains(callbackLine), "an ask timed out into a callback")
    }

    /// Unattended: the agent never asks; it promises a callback and the notes say so.
    func testUnattendedCallForMeComesBackAsACallback() throws {
        try requireReceptionist("offer")
        let before = startCallForMe(attended: false)

        sayAfterOpening(0)
        human?.tell("Stay quiet: the agent says it will call back, then hangs up.")
        waitForReceptionistCaption()
        expectNotes("The agent will need to call back")
        XCTAssertFalse(app.element("ask.question").exists, "an unattended call never asks")
        if let log {
            XCTAssertEqual(Array(log.spokenLines().dropFirst(before.count).prefix(3)), [intro, opening, callbackLine])
        }
    }

    // MARK: Steps

    private func launch() {
        app = XCUIApplication()
        app.launchArguments = ["-IsharaDriver", "live", "-IsharaRecognition", "pipeline", "-IsharaSampleSigns", clips]
        app.launch()
    }

    /// The server log names the receptionist's script; each test needs its own. On a real
    /// call the person says the lines the runner gave them.
    private func requireReceptionist(_ script: String) throws {
        guard let log else { return }
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
    /// meanwhile, taps SEND and expects the agent to speak exactly that draft: in the server
    /// log locally, as Delivered and the user's caption on a real call.
    ///
    /// Locally the draft is the template, `expected`. The deployed backend may word it with
    /// the LLM (its validator keeps every chip's meaning): a template draft must still be
    /// `expected` exactly, an LLM one must mention `words`.
    @discardableResult
    private func sendDraft(expecting expected: String, mentioning words: [String], spokenSoFar spoken: inout [String],
                           label: String, file: StaticString = #filePath, line: UInt = #line) -> String {
        let chipsShown = Date()
        let shown: String
        if let log {
            app.waitFor(app.element("call.draft"), labelContains: ": \(expected)", timeout: 20, file: file, line: line)
            shown = draftText()
            XCTAssertEqual(shown, expected, "the draft on screen", file: file, line: line)
            XCTAssertEqual(log.spokenLines(), spoken, "the backend spoke before SEND", file: file, line: line)
        } else {
            shown = settledDraft(file: file, line: line)
            if app.element("call.draft").label.hasPrefix("Draft from Template: ") {
                XCTAssertEqual(shown, expected, "the template draft on screen", file: file, line: line)
            } else {
                for word in words {
                    XCTAssertTrue(shown.lowercased().contains(word), "the LLM draft “\(shown)” lost “\(word)”",
                                  file: file, line: line)
                }
            }
        }
        timings.append(("\(label): last chip → draft", Date().timeIntervalSince(chipsShown)))
        XCTAssertEqual(captions("caption.you", containing: shown), 0,
                       "the draft was spoken before SEND", file: file, line: line)
        app.keepScreenshot("e2e-\(label)-draft", in: self)

        let tapped = Date()
        app.sendAndExpectDelivered(shown, file: file, line: line)
        timings.append(("\(label): SEND → Delivered on screen", Date().timeIntervalSince(tapped)))
        if log != nil {
            expectSpoken([shown], after: spoken, file: file, line: line)
            timings.append(("\(label): SEND → spoken in the server log", Date().timeIntervalSince(tapped)))
        }
        spoken.append(shown)
        return shown
    }

    /// The draft once it has stood unchanged for 3 s: an LLM draft for fewer chips can show
    /// first, and nothing marks which chips a draft is for. Nothing may be said meanwhile.
    private func settledDraft(file: StaticString = #filePath, line: UInt = #line) -> String {
        let saidBefore = newest("caption.you")
        var last = ""
        var since = Date()
        waitUntil("a draft that stands for 3 s", timeout: 30, file: file, line: line) {
            let label = newest("call.draft")
            if label != last {
                last = label
                since = Date()
            }
            XCTAssertEqual(newest("caption.you"), saidBefore, "something was said before SEND", file: file, line: line)
            return label.hasPrefix("Draft from ") && Date().timeIntervalSince(since) >= 3
        }
        return draftText()
    }

    /// How many caption rows with this identifier contain `text`, in one query: reading row
    /// by row can lose a row that scrolls away in between ("No matches found for Element").
    private func captions(_ identifier: String, containing text: String) -> Int {
        app.descendants(matching: .any)
            .matching(NSPredicate(format: "identifier == %@ AND label CONTAINS %@", identifier, text)).count
    }

    /// The newest row's label for `identifier`, or "" when there is none.
    private func newest(_ identifier: String) -> String {
        (try? app.element(identifier).snapshot())?.label ?? ""
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

        let before = spokenLines()
        let approve = app.buttons["brief.approve"]
        XCTAssertTrue(approve.waitForExistence(timeout: 5))
        approve.tap()
        waitUntilAnswered()
        return before
    }

    /// Waits for the call to be answered: the disclosure Bolna plays on pick-up shows as
    /// the agent's caption. On a real call, tells the person to pick up.
    private func waitUntilAnswered(file: StaticString = #filePath, line: UInt = #line) {
        let disclosed = { self.captions("caption.agent", containing: "sign-language app") > 0 }
        guard let human else {
            waitUntil("the disclosure as the agent's caption", timeout: 30, file: file, line: line, disclosed)
            return
        }
        human.tell("RING: your phone rings from Ishara's calling number (a Bolna number). "
            + "ANSWER and say nothing yet; you hear “\(intro)”")
        let dialled = Date()
        human.waitFor("the call to be answered", file: file, line: line, disclosed)
        timings.append(("dialled → answered (disclosure on screen)", Date().timeIntervalSince(dialled)))
    }

    /// The `index`th line of a real receptionist, after the agent's opening.
    private func sayAfterOpening(_ index: Int) {
        guard let human else { return }
        human.tell("SAY NOW (once the agent has said “\(opening)”): “\(human.line(index))”")
    }

    /// The newest receptionist caption, to tell the next one apart from it.
    private func receptionistCaption() -> String { newest("caption.receptionist") }

    /// The receptionist's `index`th line, heard as a new caption after `previous`. Locally the
    /// stand-in says `scripted` by itself; a real person is told to say their line once the
    /// voice has said `agentLine`, and Deepgram's transcript is matched by `keywords`.
    private func hearReceptionist(_ index: Int, scripted: String, keywords: [String], after previous: String,
                                  once agentLine: String, file: StaticString = #filePath, line: UInt = #line) {
        guard let human else {
            app.waitFor(app.element("caption.receptionist"), labelContains: scripted, timeout: 30, file: file, line: line)
            return
        }
        let words = human.line(index)
        human.tell("SAY NOW (once the voice has said “\(agentLine)”): “\(words)”")
        let prompted = Date()
        human.waitFor("your words “\(words)” as a caption in the app", file: file, line: line) {
            let caption = self.receptionistCaption()
            guard !caption.isEmpty, caption != previous else { return false }
            return keywords.contains { caption.lowercased().contains($0) }
        }
        timings.append(("receptionist line \(index + 1): prompt → caption", Date().timeIntervalSince(prompted)))
        human.tell("  heard: “\(receptionistCaption())”")
    }

    /// Some receptionist caption on screen (a real call: within the person's wait).
    private func waitForReceptionistCaption(file: StaticString = #filePath, line: UInt = #line) {
        let shown = { !self.receptionistCaption().isEmpty }
        if let human {
            human.waitFor("your words as a caption in the app", file: file, line: line, shown)
        } else {
            waitUntil("a receptionist caption", timeout: 30, file: file, line: line, shown)
        }
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

    /// Waits for the agent's question to the user, with `answer` among its options; returns
    /// when it showed. Locally the question is the stand-in's `question`; on a real call it
    /// is Deepgram's transcript of the person, so any wording counts.
    private func waitForAsk(_ question: String, answer: String,
                            file: StaticString = #filePath, line: UInt = #line) -> Date {
        let asked = { self.app.element("ask.question").exists && self.app.buttons["ask.\(answer)"].exists }
        let shown: Date
        if let human {
            human.waitFor("the agent's question to the user (after your line)", file: file, line: line, asked)
            shown = Date()
            human.tell("  heard: “\(newest("ask.question"))”. Stay quiet: the user signs \(answer.uppercased()).")
        } else {
            app.waitFor(app.element("ask.question"), labelContains: question, timeout: 40, file: file, line: line)
            shown = Date()
            XCTAssertTrue(asked(), "no \(answer) answer", file: file, line: line)
        }
        return shown
    }

    /// The YES option's sentence, read off its button ("YES, Yes, 4 pm tomorrow works. Thank
    /// you."). Locally it is the rule brain's; the deployed LLM may name the time its own way.
    private func offeredYes(file: StaticString = #filePath, line: UInt = #line) -> String {
        let label = app.buttons["ask.yes"].label
        guard human != nil else {
            XCTAssertTrue(label.contains(yesAnswer), label, file: file, line: line)
            return yesAnswer
        }
        let sentence = label.range(of: "Yes, ").map { String(label[$0.lowerBound...]) } ?? label
        XCTAssertTrue(sentence.hasPrefix("Yes, ") && sentence.hasSuffix("works. Thank you."),
                      "the YES answer reads “\(label)”", file: file, line: line)
        return sentence
    }

    /// Signs the answer from its clip while the question is open; the agent must say the
    /// option's sentence for the user, not the timeout's callback line.
    private func answerBySigning(_ clip: String, expecting sentence: String, askedAt: Date,
                                 file: StaticString = #filePath, line: UInt = #line) {
        app.replay(clip, file: file, line: line)
        let tapped = Date()
        app.waitFor(app.element("caption.you"), labelContains: sentence, timeout: 15, file: file, line: line)
        let answered = Date().timeIntervalSince(askedAt)
        timings.append(("\(clip): clip picked → answer said", Date().timeIntervalSince(tapped)))
        timings.append(("\(clip): question shown → answer said (window 10 s)", answered))
        XCTAssertLessThan(answered, 10, "the signed answer came after the agent's 10 s question window",
                          file: file, line: line)
        XCTAssertEqual(captions("caption.agent", containing: callbackLine), 0,
                       "the question timed out into the callback line", file: file, line: line)
        XCTAssertFalse(receptionistCaption().isEmpty, "the receptionist's words never showed as a caption",
                       file: file, line: line)
        app.keepScreenshot("e2e-answered-\(clip)", in: self)
    }

    private func expectNotes(_ outcome: String, file: StaticString = #filePath, line: UInt = #line) {
        let notes = app.buttons["call.notes"]
        // A real call ends once Bolna hangs up and its webhook arrives.
        let ended = max(45, human?.wait ?? 0)
        XCTAssertTrue(notes.waitForExistence(timeout: ended), "the call did not end with a notes button", file: file, line: line)
        notes.tap()
        // The outcome's icon shares its identifier, so read the text itself.
        app.waitFor(app.staticTexts["notes.outcome"], labelContains: outcome, timeout: 30, file: file, line: line)
        human?.tell("  notes: “\(app.staticTexts["notes.outcome"].label)”")
        if callsRealBolna {
            // Bolna's summary comes with its final webhook, 8–16 s after the line drops. Ending
            // the test before that quits the app after its first notes fetch (28 Oct calls).
            let summary = app.element("notes.bolnaSummary")
            XCTAssertTrue(app.swipedUntilExists(summary, timeout: 30), "Bolna's summary never reached the notes",
                          file: file, line: line)
            human?.tell("  Bolna's summary is on the notes")
        }
        app.keepScreenshot("e2e-notes", in: self)
    }

    /// What the local stand-in Bolna has voiced so far; a real call has no log to read here.
    private func spokenLines() -> [String] { log?.spokenLines() ?? [] }

    /// The local server's spoken lines must be exactly `before + lines`, eventually. A real
    /// call has no server log here: Delivered and the captions are checked instead.
    private func expectSpoken(_ lines: [String], after before: [String],
                              file: StaticString = #filePath, line: UInt = #line) {
        guard let log else { return }
        waitUntil("the backend to speak \(lines)", timeout: 30, file: file, line: line) {
            log.spokenLines() == before + lines
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
