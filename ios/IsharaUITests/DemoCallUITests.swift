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
        startCall()

        // Turn 1: hello · doctor · tomorrow → LLM draft. Nothing is spoken until SEND.
        waitForDraft(containing: turn1)
        XCTAssertEqual(element("caption.you").exists, false, "a reply was spoken before SEND")
        sendAndExpectDelivered(turn1)

        // Turn 2: the receptionist's caption.
        waitFor(element("caption.receptionist"), labelContains: "We have 4 pm tomorrow. Does that work?")

        // Turn 3: no · afternoon · morning, then the wrong chip is removed with ✕.
        waitForDraft(containing: "In the morning")
        let wrongChip = app.buttons["chip.afternoon"]
        XCTAssertTrue(wrongChip.exists)
        wrongChip.tap()
        waitUntil("the afternoon chip to go away") { !wrongChip.exists }
        XCTAssertTrue(app.buttons["chip.no"].exists)
        XCTAssertTrue(app.buttons["chip.morning"].exists)
        waitForDraft(containing: turn3)
        sendAndExpectDelivered(turn3)

        // Turn 4: the receptionist offers 10:30.
        waitFor(element("caption.receptionist"), labelContains: "Yes, 10:30 tomorrow morning.")

        // Turn 5: yes · [?] · thankyou. The unsure chip shows but isn't spoken.
        waitForDraft(containing: turn5)
        XCTAssertTrue(app.buttons["chip.unsure"].exists)
        sendAndExpectDelivered(turn5)
        XCTAssertFalse(element("caption.you").label.contains("?"), "the unsure chip leaked into the spoken reply")

        // Turn 6: End. Nothing more can be sent; Back to Home returns to screen 1.
        app.buttons["call.end"].tap()
        waitFor(element("call.endedPanel"), labelContains: "You ended the call")
        XCTAssertFalse(app.buttons["call.send"].exists)
        app.buttons["call.backHome"].tap()
        XCTAssertTrue(app.buttons["home.call"].waitForExistence(timeout: 5))
    }

    func testNotDeliveredReplyIsOnlyResentAfterSendIsTappedAgain() {
        launch(extraArguments: ["-IsharaFakeNotDelivered", "YES"])
        startCall()

        waitForDraft(containing: turn1)
        sendAndExpectDelivered(turn1)

        waitForDraft(containing: "In the morning")
        app.buttons["chip.afternoon"].tap()
        waitForDraft(containing: turn3)
        app.buttons["call.send"].tap()

        // The fake call reports the first turn-3 reply as not delivered.
        waitFor(element("call.deliveryBanner"), labelContains: "Not delivered")
        waitForDraft(containing: turn3)
        XCTAssertFalse(element("caption.you").label.contains(turn3), "a failed reply was shown as spoken")

        sendAndExpectDelivered(turn3)
    }

    // MARK: Steps

    private func launch(extraArguments: [String] = []) {
        app = XCUIApplication()
        // Halves every fake-call and Get ready timer. Faster scales made the
        // Delivered banner flash by between polls.
        app.launchArguments = ["-IsharaFakeTimeScale", "0.5"] + extraArguments
        app.launch()
    }

    private func startCall() {
        let call = app.buttons["home.call"]
        XCTAssertTrue(call.waitForExistence(timeout: 10))
        call.tap()

        let start = app.buttons["getReady.start"]
        XCTAssertTrue(start.waitForExistence(timeout: 5))
        XCTAssertFalse(start.isEnabled, "Start call was enabled before the checks passed")
        waitUntil("Start call to be enabled") { start.isEnabled }
        start.tap()

        let send = app.buttons["call.send"]
        XCTAssertTrue(send.waitForExistence(timeout: 5))
        XCTAssertFalse(send.isEnabled, "SEND was enabled without a draft")
    }

    private func sendAndExpectDelivered(_ sentence: String, file: StaticString = #filePath, line: UInt = #line) {
        let send = app.buttons["call.send"]
        XCTAssertTrue(send.isEnabled, "SEND was disabled with a draft", file: file, line: line)
        send.tap()
        waitFor(element("call.deliveryBanner"), labelContains: "Delivered", file: file, line: line)
        waitFor(element("caption.you"), labelContains: sentence, file: file, line: line)
        XCTAssertFalse(element("call.draft").label.contains(sentence),
                       "the spoken draft was not wiped", file: file, line: line)
    }

    // MARK: Helpers

    private func element(_ identifier: String) -> XCUIElement {
        // Several caption rows share an identifier; the newest one is last.
        app.descendants(matching: .any).matching(identifier: identifier).allElementsBoundByIndex.last
            ?? app.descendants(matching: .any)[identifier]
    }

    private func waitForDraft(containing text: String, file: StaticString = #filePath, line: UInt = #line) {
        waitFor(element("call.draft"), labelContains: text, file: file, line: line)
    }

    private func waitFor(_ element: @autoclosure () -> XCUIElement, labelContains text: String,
                         file: StaticString = #filePath, line: UInt = #line) {
        waitUntil("an element whose label contains \u{201C}\(text)\u{201D}", file: file, line: line) {
            let current = element()
            return current.exists && current.label.contains(text)
        }
    }

    /// Polls faster than XCTNSPredicateExpectation so short-lived states such as
    /// the Delivered banner aren't missed.
    private func waitUntil(_ description: String, timeout: TimeInterval = 20,
                           file: StaticString = #filePath, line: UInt = #line,
                           _ condition: () -> Bool) {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if condition() { return }
            Thread.sleep(forTimeInterval: 0.1)
        }
        XCTFail("Timed out waiting for \(description)", file: file, line: line)
    }
}
