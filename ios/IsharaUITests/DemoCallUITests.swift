import XCTest

/// Walks the rehearsed PLAN §1 clinic call through the real screens, driven by
/// the fake call at a faster time scale. Each turn checks the safety rules the
/// demo is meant to show: nothing is spoken before SEND, the wrong chip is
/// removed before SEND, and the unsure chip never reaches the spoken sentence.
@MainActor
final class DemoCallUITests: XCTestCase {
    private let turn1 = "Hello, I'd like a doctor's appointment tomorrow."
    private let turn3 = "No, sorry, 4 pm doesn't work. Is there anything tomorrow morning?"
    private let turn5 = "Yes, 10:30 tomorrow morning works. Thank you."

    private var app: XCUIApplication!

    override func setUp() async throws {
        continueAfterFailure = false
    }

    func testRehearsedClinicCallEndToEnd() {
        launch()
        walkRehearsedClinicCall()
    }

    /// The same call at a large accessibility text size, where the draft used to hide
    /// behind the action bar while SEND was enabled.
    func testRehearsedClinicCallAtAccessibilityTextSize() {
        launch(extraArguments: Self.accessibilityLarge)
        walkRehearsedClinicCall()
    }

    /// Every state where SEND or STOP acts on a sentence, at a large and at the largest
    /// accessibility text size: the sentence must be wholly readable right above the button.
    func testSentenceStaysBesideSendAndStopAtAccessibilityTextSizes() {
        for textSize in [Self.accessibilityLarge, Self.accessibilityLargest] {
            for (fixture, sentence) in [("signing", "No. In the afternoon, please. In the morning, please."),
                                        ("notDelivered", turn3)] {
                launch(extraArguments: textSize + ["-IsharaFixture", fixture])
                let send = app.buttons["call.send"]
                XCTAssertTrue(send.waitForExistence(timeout: 10))
                XCTAssertTrue(send.isEnabled, "SEND should be enabled in the \(fixture) fixture")
                XCTAssertTrue(app.element("call.draft").label.contains(sentence))
                app.assertFullyVisible("call.draft", above: "call.send")
            }

            launch(extraArguments: textSize + ["-IsharaFixture", "speaking"])
            XCTAssertTrue(app.buttons["call.stop"].waitForExistence(timeout: 10))
            XCTAssertTrue(app.element("call.speaking").label.contains(turn3))
            app.assertFullyVisible("call.speaking", above: "call.stop")
        }
    }

    // MARK: Not delivered

    func testNotDeliveredReplyIsOnlyResentAfterSendIsTappedAgain() {
        launch(extraArguments: ["-IsharaFakeNotDelivered", "YES"])
        app.startCall()

        app.waitForDraft(containing: turn1)
        app.sendAndExpectDelivered(turn1)

        app.waitForDraft(containing: "In the morning")
        app.buttons["chip.afternoon"].tap()
        app.waitForDraft(containing: turn3)
        app.buttons["call.send"].tap()

        // The fake call reports the first turn-3 reply as not delivered.
        app.waitFor(app.element("call.deliveryBanner"), labelContains: "Not delivered")
        app.waitForDraft(containing: turn3)
        XCTAssertFalse(app.element("caption.you").label.contains(turn3), "a failed reply was shown as spoken")

        app.sendAndExpectDelivered(turn3)
    }

    // MARK: Timers

    /// At a fast clock Get ready finishes, and the first draft arrives, before the test first
    /// reads the screen. The call must still start with its rules checked (issue #31).
    func testCallStartsWhenTheTimersFinishBeforeTheFirstLook() {
        launch(timeScale: 0.05)
        app.startCall()
        app.waitForDraft(containing: turn1)
    }

    /// Start call stays disabled while Get ready is checking. The slow clock keeps the checks
    /// going for over a minute, far longer than the test takes to look.
    func testStartCallStaysDisabledWhileTheChecksRun() {
        launch(timeScale: 20)
        let call = app.buttons["home.call"]
        XCTAssertTrue(call.waitForExistence(timeout: 10))
        call.tap()
        let start = app.buttons["getReady.start"]
        XCTAssertTrue(start.waitForExistence(timeout: 5))
        let checks = app.getReadyChecks()
        XCTAssertFalse(checks.isEmpty, "the checklist is missing")
        XCTAssertTrue(checks.allSatisfy { !$0.passed }, "a check passed already: \(checks)")
        XCTAssertFalse(start.isEnabled, "Start call was enabled before the checks passed")
    }

    // MARK: Steps

    private static let accessibilityLarge = [
        "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityL",
    ]
    private static let accessibilityLargest = [
        "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL",
    ]

    private func walkRehearsedClinicCall() {
        app.startCall()

        // Turn 0: the agent's disclosure, the only line said without a SEND at the start.
        app.waitFor(app.element("caption.agent"), labelContains: "calling for a Deaf caller")

        // Turn 1: hello · doctor · tomorrow → LLM draft. Nothing is spoken until SEND.
        app.waitForDraft(containing: turn1)
        XCTAssertEqual(app.element("caption.you").exists, false, "a reply was spoken before SEND")
        app.sendAndExpectDelivered(turn1)

        // Turn 2: the receptionist's caption.
        app.waitFor(app.element("caption.receptionist"), labelContains: "We have 4 pm tomorrow. Does that work?")

        // Turn 3: no · afternoon · morning, then the wrong chip is removed with ✕.
        app.waitForDraft(containing: "In the morning")
        let wrongChip = app.buttons["chip.afternoon"]
        XCTAssertTrue(wrongChip.exists)
        app.waitUntilClearOfActionBar("chip.afternoon")
        wrongChip.tap()
        waitUntil("the afternoon chip to go away") { !wrongChip.exists }
        XCTAssertTrue(app.buttons["chip.no"].exists)
        XCTAssertTrue(app.buttons["chip.morning"].exists)
        app.waitForDraft(containing: turn3)
        app.sendAndExpectDelivered(turn3)

        // Turn 4: the receptionist offers 10:30.
        app.waitFor(app.element("caption.receptionist"), labelContains: "Yes, 10:30 tomorrow morning.")

        // Turn 5: yes · [?] · thankyou. The unsure chip shows but isn't spoken.
        app.waitForDraft(containing: turn5)
        XCTAssertTrue(app.buttons["chip.unsure"].exists)
        app.sendAndExpectDelivered(turn5)
        XCTAssertFalse(app.element("caption.you").label.contains("?"), "the unsure chip leaked into the spoken reply")

        // Turn 6: End. Nothing more can be sent; Back to Home returns to screen 1.
        app.buttons["call.end"].tap()
        app.waitFor(app.element("call.endedPanel"), labelContains: "You ended the call")
        XCTAssertFalse(app.buttons["call.send"].exists)
        // The captions stay as a read-only transcript of the call.
        XCTAssertTrue(app.element("caption.you").label.contains(turn5), "the transcript was wiped on End")
        XCTAssertTrue(app.element("caption.receptionist").label.contains("Yes, 10:30 tomorrow morning."))
        XCTAssertTrue(app.element("caption.agent").label.contains("Goodbye"), "the agent's goodbye is in the transcript")
        app.buttons["call.backHome"].tap()
        XCTAssertTrue(app.buttons["home.call"].waitForExistence(timeout: 5))
    }

    /// After Back to Home the call is in Recent calls; its row opens the captions, read only.
    func testALiveCallStaysInRecentCallsWithItsCaptions() {
        launch()
        app.startCall()
        app.waitForDraft(containing: turn1)
        app.buttons["call.end"].tap()
        app.waitFor(app.element("call.endedPanel"), labelContains: "You ended the call")
        app.buttons["call.backHome"].tap()

        let row = app.recentCallRow()
        XCTAssertTrue(row.label.contains("City Clinic"), row.label)
        XCTAssertTrue(row.label.contains("You signed the call"), row.label)
        row.tap()
        app.waitFor(app.element("notes.outcome"), labelContains: "You signed the call")
        XCTAssertTrue(app.scrolledToText(containing: "Ishara (voice), Hello, I'm calling for a Deaf caller").exists,
                      "the disclosure caption is missing")
        XCTAssertTrue(app.scrolledToText(containing: "Ishara (voice), Thank you for your time. Goodbye.").exists,
                      "the goodbye caption is missing")
        XCTAssertFalse(app.element("call.send").exists, "a saved call can't send anything")
        app.keepScreenshot("recent-call-live", in: self)
    }

    /// The default 0.5 halves every fake-call and Get ready timer. Faster scales made the
    /// Delivered banner flash by between polls.
    private func launch(timeScale: Double = 0.5, extraArguments: [String] = []) {
        app = XCUIApplication()
        app.launchArguments = EdgeCaseLaunch.freshHistory + ["-IsharaFakeTimeScale", String(timeScale)] + extraArguments
        app.launch()
    }
}
