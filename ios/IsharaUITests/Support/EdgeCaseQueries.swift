import XCTest

/// Launch switches and checks shared by the edge-case UI tests
/// (`CallEdgeCaseUITests`, `DelegatedEdgeCaseUITests`).
enum EdgeCaseLaunch {
    /// Halves the fake call's timers, like `DemoCallUITests`; faster scales let short-lived
    /// banners flash by between polls.
    static let halfSpeed = ["-IsharaFakeTimeScale", "0.5"]
    static let largestText = ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]

    static func fixture(_ name: String) -> [String] { ["-IsharaFixture", name] }
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

    /// A text containing `text`, scrolled into view if it is further down a list.
    func scrolledToText(containing text: String, swipes: Int = 5) -> XCUIElement {
        let match = staticTexts.containing(NSPredicate(format: "label CONTAINS %@", text)).firstMatch
        for _ in 0..<swipes where !(match.exists && match.isHittable) { swipeUp() }
        return match
    }

    /// A screenshot kept in the test results (export with `xcresulttool export attachments`).
    func keepScreenshot(_ name: String, in testCase: XCTestCase) {
        let attachment = XCTAttachment(screenshot: screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        testCase.add(attachment)
    }
}
