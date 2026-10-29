import XCTest

/// The PLAN §1 clinic call against the backend's free local demo server
/// (`backend/scripts/local_demo.py`): the real backend code, template drafts and a
/// scripted stand-in for Bolna. Nothing is dialled and no paid service is reached.
///
/// Skipped unless the server is up and the app was built against it:
///
///     # backend/: python -m scripts.local_demo --port 8799 --delay 0.3
///     # ios/Ishara/Config/Secrets.xcconfig:
///     #   ISHARA_BACKEND_URL = http:/$()/127.0.0.1:8799
///     #   ISHARA_APP_TOKEN = ishara-local-demo
///     TEST_RUNNER_ISHARA_LOCAL_BACKEND=1 \
///     TEST_RUNNER_ISHARA_LOCAL_BACKEND_LOG=/tmp/local-demo.log \
///     xcodebuild … -only-testing:IsharaUITests/LocalBackendCallUITests test
///
/// `ISHARA_LOCAL_BACKEND_LOG` is optional: the server's stdout, redirected to a file.
/// With it, the test also checks the stand-in Bolna spoke nothing before each SEND.
@MainActor
final class LocalBackendCallUITests: XCTestCase {
    // backend/app/templates.py for these chips and the doctor_appointment purpose.
    private let turn1 = "Hello, I'd like a doctor's appointment tomorrow."
    private let turn3 = "No, sorry, that doesn't work. Is there anything in the morning?"
    private let turn5 = "Yes, that works. Thank you."
    // backend/fakes/scripted_call.py RECEPTIONIST_LINES.
    private let receptionist2 = "We have 4 pm tomorrow. Does that work?"
    private let receptionist4 = "Yes, 10:30 tomorrow morning."
    // backend/app/markers.py DISCLOSURE and GOODBYE: the agent's static lines.
    private let intro = "Hello, I'm calling for a Deaf caller who is using Ishara, a sign-language app. "
        + "Their replies may take a few seconds."
    private let goodbye = "Thank you for your time. Goodbye."

    private var app: XCUIApplication!
    private var serverLog: LocalBackendLog?

    override func setUp() async throws {
        let environment = ProcessInfo.processInfo.environment
        try XCTSkipUnless(environment["ISHARA_LOCAL_BACKEND"] == "1",
                          "set TEST_RUNNER_ISHARA_LOCAL_BACKEND=1 once the local demo backend is up")
        serverLog = environment["ISHARA_LOCAL_BACKEND_LOG"].map { LocalBackendLog(url: URL(fileURLWithPath: $0)) }
        continueAfterFailure = false
    }

    func testClinicCallThroughTheLocalBackend() {
        app = XCUIApplication()
        // Turn 1 comes from the scripted recognizer once signing starts; later turns
        // use the simulator's replay menu, since the script plays only once.
        app.launchArguments = EdgeCaseLaunch.freshHistory + ["-IsharaDriver", "live", "-IsharaRecognition", "scripted",
                                                             "-IsharaReplay", "hello,doctor,tomorrow"]
        app.launch()
        let spokenBefore = spokenLines()
        app.startCall()

        // Placing the call: the agent's static introduction is the only thing said
        // without a SEND.
        expectSpoken(intro, after: spokenBefore)
        let spokenAtStart = spokenBefore + [intro]

        // Turn 1: hello · doctor · tomorrow → the backend's template draft.
        app.waitFor(app.element("call.status"), labelContains: "In call")
        app.waitForDraft(containing: turn1)
        expectChips(["hello", "doctor", "tomorrow"])
        XCTAssertFalse(app.element("caption.you").exists, "a reply was spoken before SEND")
        expectNothingSpoken(since: spokenAtStart)
        screenshot("e2e-1-draft")
        app.sendAndExpectDelivered(turn1)
        expectSpoken(turn1, after: spokenAtStart)

        // Turn 2: the receptionist's line arrives as a backend caption.
        app.waitFor(app.element("caption.receptionist"), labelContains: receptionist2)
        screenshot("e2e-2-caption")

        // Turn 3: no · afternoon · morning, then the wrong chip is removed with ✕.
        let spokenAfterTurn1 = spokenLines()
        replay(["no", "afternoon", "morning"])
        let wrongChip = app.buttons["chip.afternoon"]
        wrongChip.tap()
        waitUntil("the afternoon chip to go away") { !wrongChip.exists }
        app.waitForDraft(containing: turn3)
        expectNothingSpoken(since: spokenAfterTurn1)
        screenshot("e2e-3-draft")
        app.sendAndExpectDelivered(turn3)
        expectSpoken(turn3, after: spokenAfterTurn1)

        // Turn 4: the receptionist offers 10:30.
        app.waitFor(app.element("caption.receptionist"), labelContains: receptionist4)

        // Turn 5: yes · [?] · thank you. The unsure chip shows but isn't sent.
        let spokenAfterTurn3 = spokenLines()
        replay(["yes", "?", "thankyou"])
        XCTAssertTrue(app.buttons["chip.unsure"].exists)
        app.waitForDraft(containing: turn5)
        expectNothingSpoken(since: spokenAfterTurn3)
        screenshot("e2e-5-draft")
        app.sendAndExpectDelivered(turn5)
        expectSpoken(turn5, after: spokenAfterTurn3)
        XCTAssertFalse(app.element("caption.you").label.contains("?"), "the unsure chip leaked into the spoken reply")

        // Turn 6: End → Bolna's static goodbye. Nothing more can be sent.
        app.buttons["call.end"].tap()
        app.waitFor(app.element("call.endedPanel"), labelContains: "You ended the call")
        XCTAssertFalse(app.buttons["call.send"].exists)
        screenshot("e2e-6-ended")
        expectSpoken(goodbye, after: spokenAtStart + [turn1, turn3, turn5])
    }

    // MARK: Steps

    /// Plays each result through the replay menu, waiting for its chip.
    private func replay(_ options: [String], file: StaticString = #filePath, line: UInt = #line) {
        for option in options {
            let menu = app.buttons["replayMenu"]
            XCTAssertTrue(menu.waitForExistence(timeout: 5), file: file, line: line)
            menu.tap()
            let item = app.buttons.matching(NSPredicate(format: "label == %@", option)).firstMatch
            XCTAssertTrue(item.waitForExistence(timeout: 5), "no replay option \(option)", file: file, line: line)
            item.tap()
            let chip = app.buttons["chip.\(option == "?" ? "unsure" : option)"]
            XCTAssertTrue(chip.waitForExistence(timeout: 10), "no chip for \(option)", file: file, line: line)
        }
    }

    private func expectChips(_ signs: [String], file: StaticString = #filePath, line: UInt = #line) {
        for sign in signs {
            XCTAssertTrue(app.buttons["chip.\(sign)"].exists, "missing chip \(sign)", file: file, line: line)
        }
    }

    private func screenshot(_ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    // MARK: Server log

    /// What the stand-in Bolna has spoken so far, minus the holding line; empty without the log.
    private func spokenLines() -> [String] {
        serverLog?.spokenLines() ?? []
    }

    private func expectNothingSpoken(since before: [String], file: StaticString = #filePath, line: UInt = #line) {
        guard serverLog != nil else { return }
        XCTAssertEqual(spokenLines(), before, "the backend spoke before SEND", file: file, line: line)
    }

    private func expectSpoken(_ sentence: String, after before: [String],
                              file: StaticString = #filePath, line: UInt = #line) {
        guard serverLog != nil else { return }
        waitUntil("the backend to speak \u{201C}\(sentence)\u{201D}", file: file, line: line) {
            spokenLines() == before + [sentence]
        }
    }
}
