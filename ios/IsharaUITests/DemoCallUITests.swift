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
        app.startCall()

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
        app.buttons["call.backHome"].tap()
        XCTAssertTrue(app.buttons["home.call"].waitForExistence(timeout: 5))
    }

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

    // MARK: Steps

    private func launch(extraArguments: [String] = []) {
        app = XCUIApplication()
        // Halves every fake-call and Get ready timer. Faster scales made the
        // Delivered banner flash by between polls.
        app.launchArguments = ["-IsharaFakeTimeScale", "0.5"] + extraArguments
        app.launch()
    }
}
