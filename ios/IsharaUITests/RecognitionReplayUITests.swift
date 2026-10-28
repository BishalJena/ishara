import XCTest

/// Real sign videos through the whole in-app recognition chain, in the simulator: Get ready
/// calibrates on `SampleSigns/rest.mov`, then each clip is played from the "Replay a sign" menu
/// through the start/stop detector, the segment classifier (Holistic Landmarker → LiteRT ASL
/// model → `LogitsMatcher`) and the framing guard, and the screen is read back.
///
/// Opt-in, because the clips are third-party videos that are never committed. Build the set as
/// `ios/Ishara/LocalAssets/README.md` says (clips in `LocalAssets/SampleSigns`, plus the
/// `expected.csv` the parity harness and `asl_summary.py --csv` write), rebuild, then:
///
///     TEST_RUNNER_ISHARA_REPLAY_CLIPS=$PWD/ios/Ishara/LocalAssets/SampleSigns xcodebuild test ... \
///       -only-testing:IsharaUITests/RecognitionReplayUITests
///
/// Every clip must show what the whole-clip parity run decided (same category and sign), or
/// the explained difference listed in `app-expected.csv`; one sign never gives two results,
/// and no negative ever becomes a chip. Screenshots and a result table are attached.
@MainActor
final class RecognitionReplayUITests: XCTestCase {
    private var app: XCUIApplication!

    override func setUp() async throws {
        continueAfterFailure = true
    }

    func testEachReplayedClipShowsTheExpectedResult() throws {
        let clips = try clips()
        launch()
        startCall()

        var table = ["clip | word | whole clip | expected in app | app showed | why it differs"]
        for clip in clips {
            app.clearAttempt()
            app.replay(clip.name)
            let shown = app.outcomes()
            app.screenshot(named: clip.name, in: self)
            let showed = shown.isEmpty ? "nothing" : shown.map(\.description).joined(separator: " + ")
            table.append("\(clip.name) | \(clip.word) | \(clip.wholeClip) | \(clip.expected.text) | \(showed) | \(clip.reason ?? "")")

            if clip.isNegative {
                XCTAssertFalse(shown.contains { $0.category == "chip" }, "negative \(clip.name) became a chip: \(showed)")
            } else {
                XCTAssertFalse(shown.contains { $0.category == "chip" && $0.gloss != clip.word },
                               "\(clip.name) became a chip for another sign: \(showed)")
            }
            XCTAssertLessThanOrEqual(shown.count, 1, "\(clip.name): one sign gave several results: \(showed)")
            XCTAssertEqual(shown.first?.category, clip.expected?.category,
                           "\(clip.name): app showed \(showed), expected \(clip.expected.text)")
            XCTAssertEqual(shown.first?.gloss, clip.expected?.gloss,
                           "\(clip.name): app showed \(showed), expected \(clip.expected.text)")
        }
        let report = XCTAttachment(string: table.joined(separator: "\n"))
        report.name = "replay-results"
        report.lifetime = .keepAlways
        add(report)
    }

    /// Call for me (D9): replayed signs become the brief's chips. TOMORROW must chip; MORNING
    /// (a candidate word, weak on Lifeprint clips) is used if it comes back as a chip or a tapped
    /// "Did you mean …?", and otherwise must stay silent so the user taps it instead.
    func testReplayedTomorrowAndMorningFeedTheBrief() throws {
        let clips = try clips()
        let tomorrow = try XCTUnwrap(clips.first { $0.expected == .chip("tomorrow") },
                                     "no clip in the set shows a TOMORROW chip")
        let morning = try XCTUnwrap(clips.first { $0.word == "morning" && $0.expected?.gloss == "morning" }
                                        ?? clips.first { $0.word == "morning" }, "no MORNING clip in the set")
        launch()
        openBrief()

        app.replay(tomorrow.name)
        XCTAssertTrue(app.buttons["chip.tomorrow"].waitForExistence(timeout: 15), "\(tomorrow.name) gave no TOMORROW chip")

        app.replay(morning.name)
        let shown = app.outcomes()
        app.screenshot(named: "brief-after-\(morning.name)", in: self)
        XCTAssertFalse(shown.contains { $0.category == "chip" && !["tomorrow", "morning"].contains($0.gloss ?? "") },
                       "\(morning.name) added a chip for another sign: \(shown)")
        if app.buttons["candidate.accept"].exists {
            XCTAssertFalse(app.buttons["chip.morning"].exists, "a pick-one became a chip before it was tapped")
            app.buttons["candidate.accept"].tap()
        } else if !app.buttons["chip.morning"].exists {
            // Not recognised: nothing was added, and the screen says so.
            XCTAssertTrue(app.element("brief.unsure").exists, "\(morning.name) left no chip and no \"wasn't recognised\" note")
            app.buttons["brief.add.morning"].tap()
        }
        XCTAssertTrue(app.buttons["chip.morning"].waitForExistence(timeout: 5))
        app.screenshot(named: "brief-signed-chips", in: self)

        app.buttons["brief.prepare"].tap()
        app.waitFor(app.element("brief.text"), labelContains: "Preferred: tomorrow in the morning.")
        app.screenshot(named: "brief-built-from-signs", in: self)
    }

    /// Attended Call for me (D9): a replayed YES answers the agent's open question, so the
    /// fake receptionist books (an unanswered question would time out into a callback).
    func testReplayedYesAnswersTheAgentsQuestion() throws {
        let clips = try clips()
        let yes = try XCTUnwrap(clips.first { $0.expected == .chip("yes") }, "no clip in the set shows a YES chip")
        // The fake call at a third of its speed keeps the question open for 30 s instead of 10,
        // time enough to scroll the replay menu and play the clip.
        launch(["-IsharaFakeTimeScale", "3"])
        openBrief()
        app.buttons["brief.add.tomorrow"].tap()
        app.buttons["brief.add.morning"].tap()
        app.buttons["brief.prepare"].tap()
        let approve = app.buttons["brief.approve"]
        XCTAssertTrue(approve.waitForExistence(timeout: 10))
        approve.tap()

        app.waitFor(app.element("ask.question"), labelContains: "10:30 tomorrow morning", timeout: 60)
        app.screenshot(named: "ask-card-open", in: self)
        app.replay(yes.name)

        let notes = app.buttons["call.notes"]
        XCTAssertTrue(notes.waitForExistence(timeout: 30), "the call did not end")
        app.screenshot(named: "ask-answered-by-sign", in: self)
        notes.tap()
        // The outcome's icon shares its identifier, so read the text itself.
        app.waitFor(app.staticTexts["notes.outcome"], labelContains: "Booked", timeout: 30)
        app.screenshot(named: "notes-booked", in: self)
    }

    // MARK: Steps

    private func clips() throws -> [ReplayClip] {
        guard let folder = ProcessInfo.processInfo.environment["ISHARA_REPLAY_CLIPS"] else {
            throw XCTSkip("set TEST_RUNNER_ISHARA_REPLAY_CLIPS to a labelled clip folder to run")
        }
        let clips = try ReplayClip.load(from: URL(fileURLWithPath: folder, isDirectory: true))
        XCTAssertFalse(clips.isEmpty, "no clips listed in \(folder)/\(ReplayClip.expectationsFile)")
        return clips
    }

    private func launch(_ extraArguments: [String] = []) {
        app = XCUIApplication()
        app.launchArguments = ["-IsharaRecognition", "pipeline"] + extraArguments
        app.launch()
    }

    /// Get ready calibrates on rest.mov before Start turns on.
    private func passGetReady() {
        let start = app.buttons["getReady.start"]
        XCTAssertTrue(start.waitForExistence(timeout: 5))
        waitUntil("Get ready to calibrate on rest.mov", timeout: 30) { start.isEnabled }
        app.screenshot(named: "get-ready-calibrated", in: self)
        start.tap()
    }

    /// Home → Get ready → the fake call's signing screen.
    private func startCall() {
        let call = app.buttons["home.call"]
        XCTAssertTrue(call.waitForExistence(timeout: 10))
        call.tap()
        passGetReady()
        XCTAssertTrue(app.buttons["call.send"].waitForExistence(timeout: 10))
        waitUntil("the detector to watch", timeout: 10) { self.app.cameraPillLabel.contains("Watching") }
    }

    /// Home → Call for me → Get ready → the Brief screen.
    private func openBrief() {
        let callForMe = app.buttons["home.callForMe"]
        XCTAssertTrue(callForMe.waitForExistence(timeout: 10))
        callForMe.tap()
        passGetReady()
        XCTAssertTrue(app.buttons["brief.prepare"].waitForExistence(timeout: 10))
    }
}
