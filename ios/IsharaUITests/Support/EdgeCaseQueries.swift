import XCTest

/// Launch switches and checks shared by the edge-case UI tests
/// (`CallEdgeCaseUITests`, `DelegatedEdgeCaseUITests`).
enum EdgeCaseLaunch {
    /// Halves the fake call's timers, like `DemoCallUITests`; faster scales let short-lived
    /// banners flash by between polls.
    static let halfSpeed = ["-IsharaFakeTimeScale", "0.5"]
    static let largestText = ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
    /// A standard text size: "L" (the default), "XL", "XXL" or "XXXL".
    static func textSize(_ size: String) -> [String] {
        ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategory\(size)"]
    }

    static func fixture(_ name: String) -> [String] { ["-IsharaFixture", name] }

    /// Recent calls in memory for this launch only, so calls saved by earlier runs never
    /// show on Home. Every UI test launch starts with it.
    static let freshHistory = ["-IsharaCallHistory", "memory"]
}

/// The local demo backend's pid, for the opt-in tests that stop it mid-call. Skips the test
/// unless `TEST_RUNNER_ISHARA_LOCAL_BACKEND=1` and `TEST_RUNNER_ISHARA_LOCAL_BACKEND_PID`
/// are set (see `LocalBackendCallUITests` for the server and Secrets.xcconfig set-up).
func localBackendPID() throws -> pid_t {
    let environment = ProcessInfo.processInfo.environment
    try XCTSkipUnless(environment["ISHARA_LOCAL_BACKEND"] == "1",
                      "set TEST_RUNNER_ISHARA_LOCAL_BACKEND=1 once the local demo backend is up")
    return try XCTUnwrap(environment["ISHARA_LOCAL_BACKEND_PID"].flatMap { pid_t($0) },
                         "set TEST_RUNNER_ISHARA_LOCAL_BACKEND_PID to the local demo server's pid")
}

/// "light" or "dark" from `TEST_RUNNER_ISHARA_SCREENSHOTS`, naming the screenshots; skips
/// the test when unset. The simulator's appearance is set from the host beforehand
/// (`XCUIDevice.shared.appearance` left the app light on the iOS 27 simulator).
func screenshotMode() throws -> String {
    let mode = ProcessInfo.processInfo.environment["ISHARA_SCREENSHOTS"] ?? ""
    try XCTSkipUnless(["light", "dark"].contains(mode),
                      "set TEST_RUNNER_ISHARA_SCREENSHOTS=light or dark to take screenshots")
    return mode
}

extension XCUIApplication {
    /// Every caption row with this identifier, oldest first.
    func all(_ identifier: String) -> [XCUIElement] {
        descendants(matching: .any).matching(identifier: identifier).allElementsBoundByIndex
    }

    /// How many caption rows with this identifier contain `text`.
    func count(_ identifier: String, containing text: String) -> Int {
        all(identifier).filter { $0.label.contains(text) }.count
    }

    /// Holds for `duration`, failing as soon as `condition` stops being true: proves
    /// that something does NOT happen during a pause.
    func assertStays(_ description: String, for duration: TimeInterval,
                     file: StaticString = #filePath, line: UInt = #line, _ condition: () -> Bool) {
        let deadline = Date().addingTimeInterval(duration)
        while Date() < deadline {
            guard condition() else {
                XCTFail("\(description) stopped holding", file: file, line: line)
                return
            }
            Thread.sleep(forTimeInterval: 0.1)
        }
    }

    /// Every button on screen has a spoken name: not empty and not an SF Symbol's
    /// raw name (what VoiceOver reads for an icon-only button without a label).
    func assertEveryButtonLabelled(on screen: String, file: StaticString = #filePath, line: UInt = #line) {
        let symbolName = try! NSRegularExpression(pattern: "^[a-z0-9]+(\\.[a-z0-9]+)+$")
        let visible = buttons.allElementsBoundByIndex.filter { $0.exists && !$0.frame.isEmpty }
        XCTAssertFalse(visible.isEmpty, "no buttons found on \(screen)", file: file, line: line)
        for button in visible {
            let label = button.label.trimmingCharacters(in: .whitespaces)
            let range = NSRange(label.startIndex..., in: label)
            XCTAssertFalse(label.isEmpty, "\(screen): button \(button.identifier) has no label", file: file, line: line)
            XCTAssertNil(symbolName.firstMatch(in: label, range: range),
                         "\(screen): button \(button.identifier) is read as \u{201C}\(label)\u{201D}", file: file, line: line)
        }
    }

    /// The control exists, is wholly on screen and can be tapped.
    func assertReachable(_ element: XCUIElement, _ name: String, file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertTrue(element.waitForExistence(timeout: 10), "\(name) is missing", file: file, line: line)
        XCTAssertTrue(element.isHittable, "\(name) can't be tapped", file: file, line: line)
        XCTAssertTrue(windows.firstMatch.frame.contains(element.frame),
                      "\(name) runs off screen: \(element.frame)", file: file, line: line)
    }

    /// The call screen's live camera card (a 170 pt preview in 10 pt of padding on the
    /// iPhone). The simulator's stand-in card is shorter, so the room above the action bar
    /// is what's checked: the iPhone's preview must fit there.
    static let callCameraHeight: CGFloat = 190

    /// While the agent asks the user, the camera stays in view above the action bar (the
    /// user signs the answer), and with it the simulator's replay menu.
    func assertCameraInViewAboveActionBar(file: StaticString = #filePath, line: UInt = #line) {
        let camera = element("call.camera")
        let bar = element("call.actionBar")
        XCTAssertTrue(camera.exists, "the camera card is missing", file: file, line: line)
        XCTAssertTrue(bar.exists, "the action bar is missing", file: file, line: line)
        let cameraFrame = camera.frame
        let barTop = bar.frame.minY
        XCTAssertGreaterThanOrEqual(cameraFrame.minY, windows.firstMatch.frame.minY,
                                    "the camera card runs off the top: \(cameraFrame)", file: file, line: line)
        XCTAssertLessThanOrEqual(cameraFrame.maxY, barTop,
                                 "the action bar covers the camera card: card \(cameraFrame), bar top \(barTop)",
                                 file: file, line: line)
        XCTAssertGreaterThanOrEqual(barTop - cameraFrame.minY, Self.callCameraHeight,
                                    "only \(barTop - cameraFrame.minY) pt for the camera above the action bar",
                                    file: file, line: line)
        let menu = buttons["replayMenu"]
        if menu.exists {
            XCTAssertLessThanOrEqual(menu.frame.maxY, barTop, "the replay menu is under the action bar",
                                     file: file, line: line)
        }
    }

    /// A text containing `text`, scrolled into view if it is further down a list.
    func scrolledToText(containing text: String, swipes: Int = 5) -> XCUIElement {
        let match = staticTexts.containing(NSPredicate(format: "label CONTAINS %@", text)).firstMatch
        for _ in 0..<swipes where !(match.exists && match.isHittable) { swipeUp() }
        return match
    }

    /// The newest call in Recent calls, scrolled up above Home's call buttons (which cover
    /// the end of the list, so `isHittable` alone isn't enough).
    func recentCallRow(file: StaticString = #filePath, line: UInt = #line) -> XCUIElement {
        let row = buttons.matching(identifier: "recentCalls.row").firstMatch
        let call = buttons["home.call"]
        XCTAssertTrue(call.waitForExistence(timeout: 10), file: file, line: line)
        XCTAssertTrue(row.waitForExistence(timeout: 5), "no call in Recent calls", file: file, line: line)
        for _ in 0..<5 where row.frame.maxY > call.frame.minY - 60 { swipeUp() }
        XCTAssertLessThan(row.frame.maxY, call.frame.minY, "Recent calls stay under the call buttons", file: file, line: line)
        return row
    }

    /// Waits for a row that appears at the end of a list while the screen is open, swiping
    /// up now and then: a List only shows the rows scrolled into view.
    func swipedUntilExists(_ element: XCUIElement, timeout: TimeInterval) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while !element.exists, Date() < deadline {
            swipeUp()
            Thread.sleep(forTimeInterval: 1)
        }
        return element.exists
    }

    /// A screenshot kept in the test results (export with `xcresulttool export attachments`).
    func keepScreenshot(_ name: String, in testCase: XCTestCase) {
        let attachment = XCTAttachment(screenshot: screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        testCase.add(attachment)
    }
}
