import XCTest

/// Performs the launch film's demo (docs/demo/video/SCRIPT.md §5) on the real app while the
/// simulator screen is recorded: type the number and the request, attach the health history
/// PDF from Files, call, tap a suggested reply, sign THANK YOU, read the gist, Done.
///
/// Opt-in: runs only with `TEST_RUNNER_ISHARA_FILM=1` (scripts/record-film.sh sets it), and
/// expects `Health history.pdf` in the simulator's Files, On My iPhone.
final class FilmRecordingUITests: XCTestCase {
    private var app: XCUIApplication!

    override func setUpWithError() throws {
        try XCTSkipUnless(ProcessInfo.processInfo.environment["ISHARA_FILM"] == "1", "Film recording only (scripts/record-film.sh).")
        continueAfterFailure = false
        app = XCUIApplication()
        app.launchArguments = [
            "-IsharaCallHistory", "memory", "-IsharaFlow", "steer", "-IsharaDriver", "fake", "-IsharaFilm", "1",
            "-IsharaRecognition", "scripted",
        ]
        app.launchEnvironment["ISHARA_UITEST_NAME"] = "Aarav Sharma"
        app.launch()
    }

    func testFilm() throws {
        // Home holds for a beat, the way the film opens on it.
        let number = app.textFields["setup.number"].firstMatch
        XCTAssertTrue(number.waitForExistence(timeout: 10))
        pause(2.5)

        number.tap()
        pause(0.6)
        for digit in "8041234567" {
            number.typeText(String(digit))
            pause(0.11)
        }
        pause(0.8)

        let request = app.textViews["setup.request"].firstMatch.exists
            ? app.textViews["setup.request"].firstMatch : app.textFields["setup.request"].firstMatch
        request.tap()
        pause(0.5)
        let words = "Book a follow-up with Dr. Kavita Rao for my blood pressure, this week, mornings if possible.".split(separator: " ")
        for (index, word) in words.enumerated() {
            request.typeText(index == words.count - 1 ? String(word) : "\(word) ")
            pause(0.07)
        }
        pause(1.2)

        // Attach the health history from Files.
        app.buttons["setup.attach"].tap()
        pause(0.9)
        app.buttons["File or PDF"].firstMatch.tap()
        pause(1.5)
        try pickHealthHistory()
        XCTAssertTrue(app.staticTexts["Read on this iPhone · Ishara can quote it when asked"].waitForExistence(timeout: 10))
        pause(2.2)

        app.buttons["setup.call"].tap()

        // Ishara leads; its first two lines run out their bars and are said. For the third,
        // a suggested reply replaces Ishara's proposed line while its bar is filling.
        let proposed = element(containing: "Yes, Thursday at 10:30 works. Thank you.")
        XCTAssertTrue(proposed.waitForExistence(timeout: 90), "Ishara proposes its answer to Thursday at 10:30 am")
        pause(1.6)
        app.buttons["Yes, 10:30 am works"].firstMatch.tap()

        // After the booking is confirmed, THANK YOU is signed instead of letting Ishara close.
        let closing = element(containing: "That's all, thank you so much for your help.")
        XCTAssertTrue(closing.waitForExistence(timeout: 60))
        pause(1.2)
        app.buttons["steer.sign"].tap()
        let draft = app.staticTexts["Thank you so much for your help."].firstMatch
        XCTAssertTrue(draft.waitForExistence(timeout: 10))
        pause(1.4)
        app.buttons["steer.sendSigned"].tap()

        // The gist opens by itself; read it, then Done.
        let outcome = app.staticTexts["notes.outcome"].firstMatch.exists ? app.staticTexts["notes.outcome"].firstMatch : app.otherElements["notes.outcome"].firstMatch
        XCTAssertTrue(app.buttons["notes.done"].waitForExistence(timeout: 40))
        _ = outcome.waitForExistence(timeout: 5)
        pause(5)
        app.buttons["notes.done"].tap()
        pause(3)
    }

    /// The document browser: Browse, On My iPhone, the file.
    private func pickHealthHistory() throws {
        let file = app.descendants(matching: .any).matching(NSPredicate(format: "label BEGINSWITH 'Health history'")).firstMatch
        if file.waitForExistence(timeout: 3) {
            file.tap()
            return
        }
        let browse = app.buttons["Browse"].firstMatch
        if browse.exists { browse.tap(); pause(0.8) }
        let onMyPhone = app.descendants(matching: .any).matching(NSPredicate(format: "label == 'On My iPhone'")).firstMatch
        if onMyPhone.waitForExistence(timeout: 3) { onMyPhone.tap(); pause(1) }
        XCTAssertTrue(file.waitForExistence(timeout: 5), "Health history.pdf in Files, On My iPhone")
        file.tap()
    }

    /// Any element whose label contains `text` (the proposal bar reads as one button).
    private func element(containing text: String) -> XCUIElement {
        app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", text)).firstMatch
    }

    private func pause(_ seconds: Double) {
        Thread.sleep(forTimeInterval: seconds)
    }
}
