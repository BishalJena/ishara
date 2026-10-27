import XCTest

/// Live-call edge cases (PLAN §6 T2, docs/WORKFLOW.md edge-case table) that need neither a
/// camera nor a real call, on the fake call. Each test checks the safety rule the case is
/// about: nothing is spoken without SEND, an approval speaks once, a stale or removed draft
/// can't be sent, and a drop or End leaves nothing that could still be sent.
@MainActor
final class CallEdgeCaseUITests: XCTestCase {
    private let turn1 = "Hello, I'd like a doctor's appointment tomorrow."
    private let turn3 = "No, sorry, 4 pm doesn't work. Is there anything tomorrow morning?"
    /// The template draft for no · afternoon · morning (`DemoScript.draft`).
    private let threeChipDraft = "No. In the afternoon, please. In the morning, please."

    private var app: XCUIApplication!

    override func setUp() async throws {
        continueAfterFailure = false
    }

    // MARK: Pauses

    /// Hands at rest cost nothing: with a draft ready and no tap, nothing is spoken and the
    /// draft stays exactly as it was.
    func testLongPauseSpeaksNothing() {
        launch()
        app.startCall()
        app.waitForDraft(containing: turn1)

        // 8 s at half speed is 16 s of the scripted call: past Bolna's 15 s silence line.
        app.assertStays("a silent pause", for: 8) {
            !app.element("caption.you").exists
                && app.element("call.draft").label.contains(turn1)
                && app.buttons["call.send"].isEnabled
                && !app.buttons["call.stop"].exists
        }
        XCTAssertFalse(app.element("call.deliveryBanner").exists, "a delivery result appeared without SEND")
    }

    // MARK: Chips

    /// A wrong chip removed before SEND: its draft can't be sent while the new one is being
    /// written, and its word never reaches the call.
    func testRemovedChipsDraftCanNotBeSent() {
        launch()
        app.startCall()
        app.waitForDraft(containing: turn1)
        app.sendAndExpectDelivered(turn1)

        app.waitForDraft(containing: threeChipDraft)
        app.waitUntilClearOfActionBar("chip.afternoon")
        app.buttons["chip.afternoon"].tap()

        // The shown draft described the old chips: it goes, and SEND waits for the new one
        // (which the fake call may already have sent by the time the screen is read).
        XCTAssertFalse(app.element("call.draft").label.contains(threeChipDraft), "the stale draft is still offered")
        XCTAssertTrue(!app.buttons["call.send"].isEnabled || app.element("call.draft").label.contains(turn3),
                      "SEND was enabled with a stale draft")
        app.waitForDraft(containing: turn3)
        app.sendAndExpectDelivered(turn3)
        XCTAssertEqual(app.count("caption.you", containing: "afternoon"), 0, "the removed chip was spoken")
    }

    // MARK: SEND

    /// A double tap on SEND approves the draft once: it is spoken once, and the second tap
    /// neither repeats it nor stops it.
    func testDoubleSendSpeaksOnce() {
        launch()
        app.startCall()
        app.waitForDraft(containing: turn1)

        app.buttons["call.send"].doubleTap()

        app.waitFor(app.element("call.deliveryBanner"), labelContains: "Delivered")
        XCTAssertFalse(app.element("call.deliveryBanner").label.contains("Stopped"), "the second tap stopped the reply")
        XCTAssertEqual(app.count("caption.you", containing: turn1), 1)
        // Long enough for a second approval to have been spoken.
        app.assertStays("one spoken copy", for: 3) { app.count("caption.you", containing: turn1) == 1 }
    }

    /// "Not delivered" is never resent by itself; only a new tap on SEND speaks it again.
    func testNotDeliveredIsResentOnlyOnANewTap() {
        launch(["-IsharaFakeNotDelivered", "YES"])
        app.startCall()
        app.waitForDraft(containing: turn1)
        app.sendAndExpectDelivered(turn1)
        app.waitForDraft(containing: threeChipDraft)
        app.waitUntilClearOfActionBar("chip.afternoon")
        app.buttons["chip.afternoon"].tap()
        app.waitForDraft(containing: turn3)
        app.buttons["call.send"].tap()

        app.waitFor(app.element("call.deliveryBanner"), labelContains: "Not delivered")
        app.assertStays("the unspoken reply waiting for a tap", for: 5) {
            app.count("caption.you", containing: turn3) == 0
                && !app.buttons["call.stop"].exists
                && app.element("call.draft").label.contains(turn3)
        }

        app.sendAndExpectDelivered(turn3)
        XCTAssertEqual(app.count("caption.you", containing: turn3), 1)
    }

    /// The receptionist talks over the reply being spoken: their words show as a caption,
    /// STOP stays in reach, and ordinary talk doesn't cut the reply off.
    func testReceptionistTalkingOverTheReplyDoesNotCutItOff() {
        launch(["-IsharaFakeInterrupt", "YES"])
        app.startCall()
        app.waitForDraft(containing: turn1)
        app.buttons["call.send"].tap()

        app.waitFor(app.element("caption.receptionist"), labelContains: "who's calling")
        XCTAssertTrue(app.buttons["call.stop"].exists, "STOP went away when the receptionist spoke")
        XCTAssertTrue(app.element("call.speaking").label.contains(turn1))
        app.waitFor(app.element("call.deliveryBanner"), labelContains: "Delivered")
        XCTAssertEqual(app.count("caption.you", containing: turn1), 1)
    }

    // MARK: Lost connection

    /// The backend goes away with chips and a draft on screen: the screen says so, the
    /// draft is wiped and SEND is off. When the socket comes back nothing is resent and
    /// the old draft doesn't return.
    func testLostConnectionWipesTheReplyAndResendsNothing() {
        launch(["-IsharaFakeConnectionDrop", "reconnects"])
        app.startCall()
        app.waitForDraft(containing: turn1)

        app.waitFor(app.element("call.connectionLostPanel"), labelContains: "Chips and draft were wiped")
        XCTAssertTrue(app.element("call.status").label.contains("reconnecting"))
        XCTAssertFalse(app.element("call.draft").exists, "the draft outlived the lost connection")
        XCTAssertFalse(app.buttons["chip.hello"].exists, "chips outlived the lost connection")
        XCTAssertFalse(app.buttons["call.send"].isEnabled)
        XCTAssertFalse(app.buttons["quickReply.yes"].isEnabled)
        XCTAssertTrue(app.buttons["call.end"].isHittable, "End must stay in reach")

        app.waitFor(app.element("call.status"), labelContains: "In call")
        app.assertStays("nothing resent after the reconnect", for: 4) {
            !app.element("caption.you").exists
                && !app.buttons["chip.hello"].exists
                && !app.element("call.draft").label.contains(turn1)
                && !app.buttons["call.send"].isEnabled
        }
    }

    /// The connection doesn't come back: the screen stops promising a reconnect and End
    /// still ends the call.
    func testConnectionThatStaysDownLeavesOnlyEnd() {
        launch(["-IsharaFakeConnectionDrop", "staysDown"])
        app.startCall()
        app.waitForDraft(containing: turn1)

        app.waitFor(app.element("call.connectionLostPanel"), labelContains: "couldn't be restored")
        XCTAssertFalse(app.element("call.connectionLostPanel").label.contains("Reconnecting"))
        XCTAssertFalse(app.buttons["call.send"].isEnabled)
        app.buttons["call.end"].tap()
        app.waitFor(app.element("call.endedPanel"), labelContains: "You ended the call")
        XCTAssertFalse(app.element("caption.you").exists)
    }

    /// The real backend (`backend/scripts/local_demo.py`) is stopped with a draft on screen,
    /// a stand-in for the network going away. Opt-in, set up as for
    /// `LocalBackendCallUITests`, plus the server's pid in
    /// `TEST_RUNNER_ISHARA_LOCAL_BACKEND_PID`; the test stops that process, so restart it after.
    func testBackendStoppedMidCallThroughTheLocalBackend() throws {
        let pid = try localBackendPID()
        launch(["-IsharaDriver", "live", "-IsharaRecognition", "scripted", "-IsharaReplay", "hello,doctor,tomorrow"])
        app.startCall()
        app.waitForDraft(containing: turn1)

        XCTAssertEqual(kill(pid, SIGTERM), 0, "couldn't stop the local backend (pid \(pid))")

        XCTAssertTrue(app.element("call.connectionLostPanel").waitForExistence(timeout: 15))
        XCTAssertFalse(app.element("call.draft").exists, "the draft outlived the lost connection")
        XCTAssertFalse(app.buttons["call.send"].isEnabled)
        app.waitFor(app.element("call.connectionLostPanel"), labelContains: "couldn't be restored", timeout: 60)
        XCTAssertFalse(app.element("caption.you").exists, "something was spoken without SEND")
        app.buttons["call.end"].tap()
        XCTAssertTrue(app.element("call.endedPanel").waitForExistence(timeout: 10))
    }

    // MARK: End

    /// End with a draft on screen: the call ends, the draft is wiped and never spoken.
    func testEndMidDraftSpeaksNothing() {
        launch()
        app.startCall()
        app.waitForDraft(containing: turn1)

        app.buttons["call.end"].tap()

        app.waitFor(app.element("call.endedPanel"), labelContains: "You ended the call")
        XCTAssertFalse(app.buttons["call.send"].exists)
        XCTAssertFalse(app.element("call.draft").exists, "the unsent draft outlived End")
        app.assertStays("silence after End", for: 3) { !app.element("caption.you").exists }
        XCTAssertTrue(app.element("caption.agent").label.contains("Goodbye"))
    }

    // MARK: Everywhere

    /// Every button on the live-call screens has a spoken name.
    func testEveryButtonHasAnAccessibilityLabel() {
        launch()
        XCTAssertTrue(app.buttons["home.call"].waitForExistence(timeout: 10))
        app.assertEveryButtonLabelled(on: "Home")
        app.buttons["home.call"].tap()
        XCTAssertTrue(app.buttons["getReady.start"].waitForExistence(timeout: 5))
        app.assertEveryButtonLabelled(on: "Get ready")

        for fixture in ["signing", "speaking", "notDelivered", "stopTooLate", "connectionLost", "ended"] {
            launch(EdgeCaseLaunch.fixture(fixture))
            XCTAssertTrue(app.element("call.status").waitForExistence(timeout: 10))
            app.assertEveryButtonLabelled(on: fixture)
        }
    }

    /// At the largest text size, SEND, STOP and End stay on screen and tappable.
    func testCriticalButtonsStayReachableAtTheLargestTextSize() {
        launch(EdgeCaseLaunch.largestText + EdgeCaseLaunch.fixture("signing"))
        app.assertReachable(app.buttons["call.send"], "SEND")
        app.assertReachable(app.buttons["call.end"], "End")
        app.keepScreenshot("live-signing-largest-text", in: self)

        launch(EdgeCaseLaunch.largestText + EdgeCaseLaunch.fixture("speaking"))
        app.assertReachable(app.buttons["call.stop"], "STOP")
        app.assertReachable(app.buttons["call.end"], "End")
        app.keepScreenshot("live-speaking-largest-text", in: self)

        launch(EdgeCaseLaunch.largestText + EdgeCaseLaunch.fixture("connectionLost"))
        app.assertReachable(app.buttons["call.end"], "End")
    }

    /// Screenshots of every live-call screen, kept in the results. Opt-in: set the
    /// simulator's appearance (`xcrun simctl ui <udid> appearance dark`), then run with
    /// `TEST_RUNNER_ISHARA_SCREENSHOTS=dark` (or `light`), which names the files.
    func testScreenshotsOfEveryScreen() throws {
        let mode = try screenshotMode()
        for fixture in ["home", "getReady", "signing", "composing", "speaking", "delivered", "notDelivered",
                        "stopped", "stopTooLate", "backendError", "connectionLost", "ended", "notes"] {
            launch(EdgeCaseLaunch.fixture(fixture))
            XCTAssertTrue(app.buttons.firstMatch.waitForExistence(timeout: 10))
            Thread.sleep(forTimeInterval: 1)
            app.keepScreenshot("live-\(fixture)-\(mode)", in: self)
        }
    }

    // MARK: Steps

    private func launch(_ arguments: [String] = []) {
        app = XCUIApplication()
        app.launchArguments = EdgeCaseLaunch.halfSpeed + arguments
        app.launch()
    }
}
