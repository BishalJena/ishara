import XCTest

/// Lookups and waits shared by the call UI tests.
extension XCUIApplication {
    /// Several caption rows share an identifier; the newest one is last.
    func element(_ identifier: String) -> XCUIElement {
        descendants(matching: .any).matching(identifier: identifier).allElementsBoundByIndex.last
            ?? descendants(matching: .any)[identifier]
    }

    /// Home → Get ready → Start call. Checks both screens say the call comes from
    /// Ishara's number, Start is enabled only once the checks pass and SEND only with a draft.
    ///
    /// Get ready and the first draft finish on timers that can beat the test's first look
    /// at the screen (issue #31), so each rule is read from one snapshot, never as
    /// "disabled at first look".
    func startCall(file: StaticString = #filePath, line: UInt = #line) {
        let call = buttons["home.call"]
        XCTAssertTrue(call.waitForExistence(timeout: 10), file: file, line: line)
        assertCallingNumberDisclosed(file: file, line: line)
        call.tap()

        let start = buttons["getReady.start"]
        XCTAssertTrue(start.waitForExistence(timeout: 5), file: file, line: line)
        assertCallingNumberDisclosed(file: file, line: line)
        waitUntil("Start call to be enabled", file: file, line: line) {
            let screen = screenSnapshot(file: file, line: line)
            guard screen.contains(where: { $0.identifier == "getReady.start" && $0.isEnabled }) else { return false }
            let checks = getReadyChecks(in: screen)
            XCTAssertTrue(!checks.isEmpty && checks.allSatisfy(\.passed),
                          "Start call was enabled before the checks passed: \(checks)", file: file, line: line)
            XCTAssertTrue(screen.contains { $0.label.hasPrefix("Hands at rest: calibrated") },
                          "Start call was enabled before the hands-at-rest calibration", file: file, line: line)
            return true
        }
        start.tap()

        let send = buttons["call.send"]
        XCTAssertTrue(send.waitForExistence(timeout: 5), file: file, line: line)
        let screen = screenSnapshot(file: file, line: line)
        let sendEnabled = screen.contains { $0.identifier == "call.send" && $0.isEnabled }
        let hasDraft = screen.contains { $0.identifier == "call.draft" && $0.label.hasPrefix("Draft from") }
        XCTAssertTrue(!sendEnabled || hasDraft, "SEND was enabled without a draft", file: file, line: line)
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

    /// Calls come from Ishara's calling number, never the user's own; the user must be
    /// told before placing one.
    func assertCallingNumberDisclosed(file: StaticString = #filePath, line: UInt = #line) {
        let note = element("callingNumberNote")
        XCTAssertTrue(note.exists, "the calling-number note is missing", file: file, line: line)
        XCTAssertTrue(note.label.contains("Ishara's calling number, not your own number"),
                      "the calling-number note changed: \(note.label)", file: file, line: line)
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

    /// The element is wholly in view: its top edge shows inside its scroll view, below any
    /// navigation bar, and it ends above the pinned bar.
    func isInView(_ identifier: String, above barIdentifier: String) -> Bool {
        let target = element(identifier)
        let bar = element(barIdentifier)
        guard target.exists, bar.exists else { return false }
        let frame = target.frame
        var top = windows.firstMatch.frame.minY
        let scrollView = scrollViews.containing(.any, identifier: identifier).firstMatch
        if scrollView.exists { top = max(top, scrollView.frame.minY) }
        let navigationBar = navigationBars.firstMatch
        if navigationBar.exists { top = max(top, navigationBar.frame.maxY) }
        return frame.minY >= top && target.isHittable && frame.maxY <= bar.frame.minY
    }

    /// A chip sitting under the action bar can't be seen, and a tap on it lands on
    /// the quick reply above it instead. Waits for it to be clear of the bar.
    func waitUntilClearOfActionBar(_ identifier: String, file: StaticString = #filePath, line: UInt = #line) {
        let target = element(identifier)
        let barControls = buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'quickReply.'"))
        waitUntil("\(identifier) to be clear of the action bar", timeout: 5, file: file, line: line) {
            let topOfBar = barControls.allElementsBoundByIndex.map(\.frame.minY).min() ?? .greatestFiniteMagnitude
            return target.exists && target.frame.maxY <= topOfBar
        }
    }

    /// The whole screen at one instant, flattened. Two separate queries can straddle one of
    /// the app's timers; values read from a single snapshot can't.
    func screenSnapshot(file: StaticString = #filePath, line: UInt = #line) -> [XCUIElementSnapshot] {
        do {
            var all: [XCUIElementSnapshot] = []
            var pending = [try snapshot()]
            while let next = pending.popLast() {
                all.append(next)
                pending += next.children
            }
            return all
        } catch {
            XCTFail("Couldn't snapshot the screen: \(error)", file: file, line: line)
            return []
        }
    }

    /// Get ready's checklist rows, read as "Face visible: yes" or "Face visible: checking".
    func getReadyChecks(in screen: [XCUIElementSnapshot]? = nil) -> [(label: String, passed: Bool)] {
        (screen ?? screenSnapshot()).compactMap { element in
            if element.label.hasSuffix(": yes") { return (element.label, true) }
            if element.label.hasSuffix(": checking") { return (element.label, false) }
            return nil
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
            // One snapshot per look: a caption row can scroll away between `exists` and
            // `label`, and reading a vanished row fails the test instead of returning false.
            guard let current = try? element().snapshot() else { return false }
            return current.label.contains(text)
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
