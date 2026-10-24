import XCTest

/// Lookups and waits shared by the call UI tests.
extension XCUIApplication {
    /// Several caption rows share an identifier; the newest one is last.
    func element(_ identifier: String) -> XCUIElement {
        descendants(matching: .any).matching(identifier: identifier).allElementsBoundByIndex.last
            ?? descendants(matching: .any)[identifier]
    }

    /// Home → Get ready → Start call. Checks Start waits for the checks and SEND
    /// starts disabled.
    func startCall(file: StaticString = #filePath, line: UInt = #line) {
        let call = buttons["home.call"]
        XCTAssertTrue(call.waitForExistence(timeout: 10), file: file, line: line)
        call.tap()

        let start = buttons["getReady.start"]
        XCTAssertTrue(start.waitForExistence(timeout: 5), file: file, line: line)
        XCTAssertFalse(start.isEnabled, "Start call was enabled before the checks passed", file: file, line: line)
        waitUntil("Start call to be enabled", file: file, line: line) { start.isEnabled }
        start.tap()

        let send = buttons["call.send"]
        XCTAssertTrue(send.waitForExistence(timeout: 5), file: file, line: line)
        XCTAssertFalse(send.isEnabled, "SEND was enabled without a draft", file: file, line: line)
    }

    /// Taps SEND, then expects Delivered, the sentence as the user's caption and the
    /// draft wiped. The draft must be readable right above SEND when it is tapped.
    func sendAndExpectDelivered(_ sentence: String, file: StaticString = #filePath, line: UInt = #line) {
        let send = buttons["call.send"]
        XCTAssertTrue(send.isEnabled, "SEND was disabled with a draft", file: file, line: line)
        assertFullyVisible("call.draft", above: "call.send", file: file, line: line)
        send.tap()
        waitFor(element("call.deliveryBanner"), labelContains: "Delivered", file: file, line: line)
        waitFor(element("caption.you"), labelContains: sentence, file: file, line: line)
        XCTAssertFalse(element("call.draft").label.contains(sentence),
                       "the spoken draft was not wiped", file: file, line: line)
    }

    /// The sentence a button acts on (the draft for SEND, the spoken sentence for STOP)
    /// must be wholly on screen above that button, with no action-bar control over it.
    func assertFullyVisible(_ sentenceIdentifier: String, above buttonIdentifier: String,
                            file: StaticString = #filePath, line: UInt = #line) {
        let sentence = element(sentenceIdentifier)
        let button = buttons[buttonIdentifier]
        XCTAssertTrue(sentence.exists, "\(sentenceIdentifier) is missing", file: file, line: line)
        XCTAssertTrue(sentence.isHittable, "\(sentenceIdentifier) is not visible", file: file, line: line)
        let frame = sentence.frame
        XCTAssertTrue(windows.firstMatch.frame.contains(frame),
                      "\(sentenceIdentifier) runs off screen: \(frame)", file: file, line: line)
        XCTAssertLessThanOrEqual(frame.maxY, button.frame.minY,
                                 "\(sentenceIdentifier) is not above \(buttonIdentifier)", file: file, line: line)
        let controls = buttons.matching(NSPredicate(
            format: "identifier BEGINSWITH 'quickReply.' OR identifier BEGINSWITH 'call.'"))
        for control in controls.allElementsBoundByIndex where control.frame.intersects(frame) {
            XCTFail("\(control.identifier) covers \(sentenceIdentifier)", file: file, line: line)
        }
    }

    func waitForDraft(containing text: String, timeout: TimeInterval = 20,
                      file: StaticString = #filePath, line: UInt = #line) {
        waitFor(element("call.draft"), labelContains: text, timeout: timeout, file: file, line: line)
    }

    func waitFor(_ element: @autoclosure () -> XCUIElement, labelContains text: String,
                 timeout: TimeInterval = 20, file: StaticString = #filePath, line: UInt = #line) {
        waitUntil("an element whose label contains \u{201C}\(text)\u{201D}", timeout: timeout,
                  file: file, line: line) {
            let current = element()
            return current.exists && current.label.contains(text)
        }
    }
}

/// Polls faster than XCTNSPredicateExpectation so short-lived states such as
/// the Delivered banner aren't missed.
func waitUntil(_ description: String, timeout: TimeInterval = 20,
               file: StaticString = #filePath, line: UInt = #line,
               _ condition: () -> Bool) {
    let deadline = Date().addingTimeInterval(timeout)
    while Date() < deadline {
        if condition() { return }
        Thread.sleep(forTimeInterval: 0.1)
    }
    XCTFail("Timed out waiting for \(description)", file: file, line: line)
}
