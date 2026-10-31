import XCTest

/// The steer flow on the fake driver: type the request, Call, watch Ishara's proposed line
/// fill and go out, step in by typing, see the typed line previewed and spoken, and
/// reach the gist. Nothing is dialled.
@MainActor
final class SteerCallUITests: XCTestCase {
    private var app: XCUIApplication!

    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
        app.launchArguments = ["-IsharaCallHistory", "memory", "-IsharaFlow", "steer", "-IsharaDriver", "fake"]
        app.launchEnvironment["ISHARA_UITEST_NAME"] = "Riya"
        app.launch()
    }

    func testIsharaRunsTheCallAndTheUserStepsInByTyping() throws {
        let number = app.textFields["setup.number"].firstMatch
        XCTAssertTrue(number.waitForExistence(timeout: 5))
        number.tap()
        number.typeText("9876543210")
        let request = app.textViews["setup.request"].firstMatch.exists
            ? app.textViews["setup.request"].firstMatch : app.textFields["setup.request"].firstMatch
        XCTAssertTrue(request.waitForExistence(timeout: 5))
        request.tap()
        request.typeText("Book a check-up next week, mornings only.")
        let call = app.buttons["setup.call"]
        XCTAssertTrue(call.waitForExistence(timeout: 2))
        XCTAssertTrue(call.isEnabled)
        call.tap()

        // Ishara's first proposed line appears once the receptionist has spoken.
        let proposal = app.buttons["steer.proposal"].firstMatch
        XCTAssertTrue(proposal.waitForExistence(timeout: 20), "the agent's line is proposed while the app is in front")
        attach("proposal")
        // Doing nothing: the window runs out and the line is spoken (it appears as a caption).
        XCTAssertTrue(app.staticTexts["No, 4 pm tomorrow doesn't work, sorry. Is there anything in the morning?"].waitForExistence(timeout: 15))

        // Step in by typing: the field holds the next proposal and the typed line is previewed.
        let field = app.textFields["steer.field"].firstMatch.exists
            ? app.textFields["steer.field"].firstMatch : app.textViews["steer.field"].firstMatch
        XCTAssertTrue(field.waitForExistence(timeout: 5))
        field.tap()
        field.typeText("can we do 11 instead")
        app.buttons["steer.send"].tap()
        XCTAssertTrue(app.staticTexts["Can we do 11 instead?"].waitForExistence(timeout: 10), "the typed line is previewed, then shown as the user's")
        attach("typed")

        // The call runs to its end on its own and goes on to the gist by itself.
        XCTAssertTrue(app.staticTexts["notes.outcome"].waitForExistence(timeout: 60) || app.otherElements["notes.outcome"].waitForExistence(timeout: 2))
        attach("gist")

        // One tap home, and Home is ready for the next call.
        let done = app.buttons["notes.done"]
        XCTAssertTrue(done.waitForExistence(timeout: 2))
        done.tap()
        XCTAssertTrue(app.textFields["setup.number"].firstMatch.waitForExistence(timeout: 5), "Done goes back to Home")
        let leftover = app.textFields["setup.number"].firstMatch.value as? String ?? ""
        XCTAssertTrue(leftover.isEmpty || leftover == "10-digit number", "the finished call's draft is cleared")
    }

    func testSigningWordsStayCompactAndCarryIntoAnEditableSentence() throws {
        let number = app.textFields["setup.number"].firstMatch
        XCTAssertTrue(number.waitForExistence(timeout: 5))
        number.tap()
        number.typeText("9876543210")
        let request = app.textViews["setup.request"].firstMatch.exists
            ? app.textViews["setup.request"].firstMatch : app.textFields["setup.request"].firstMatch
        request.tap()
        request.typeText("Ask about a service request.")
        app.buttons["setup.call"].tap()
        let sign = app.buttons["steer.sign"]
        XCTAssertTrue(sign.waitForExistence(timeout: 20))
        let connected = NSPredicate(format: "enabled == true")
        expectation(for: connected, evaluatedWith: sign)
        waitForExpectations(timeout: 15)
        sign.tap()
        let words = app.buttons["steer.allSignWords"]
        XCTAssertTrue(words.waitForExistence(timeout: 5))
        words.tap()
        app.buttons["signWord.hello"].tap()
        app.buttons["signWord.hello"].tap()
        app.buttons["signWord.please"].tap()
        XCTAssertEqual(app.buttons.matching(identifier: "chip.hello").count, 1)
        XCTAssertFalse(app.buttons["chip.unsure"].exists)
        attach("signing-word-review")
        let edit = app.buttons["steer.editSignedSentence"]
        XCTAssertTrue(edit.waitForExistence(timeout: 5))
        edit.tap()
        let field = app.textFields["steer.field"].firstMatch.exists
            ? app.textFields["steer.field"].firstMatch : app.textViews["steer.field"].firstMatch
        XCTAssertTrue(field.waitForExistence(timeout: 5))
        let text = field.value as? String ?? ""
        XCTAssertTrue(text.lowercased().contains("hello"))
        XCTAssertTrue(text.lowercased().contains("please"))
        attach("signing-edit-sentence")
        app.buttons["steer.end"].tap()
    }

    /// Real URLSession HTTP and WebSocket against the explicit fake-telephone server.
    /// The build must point to localhost with its test token; never a provider backend.
    func testNativeSteerCaptionsTypedReplyAndGistThroughLocalBackend() throws {
        try XCTSkipUnless(ProcessInfo.processInfo.environment["ISHARA_LOCAL_BACKEND"] == "1")
        app.terminate()
        app.launchArguments = ["-IsharaCallHistory", "memory", "-IsharaFlow", "steer", "-IsharaDriver", "live", "-IsharaRecognition", "scripted"]
        app.launch()
        let number = app.textFields["setup.number"].firstMatch
        XCTAssertTrue(number.waitForExistence(timeout: 5))
        number.tap()
        number.typeText("2" + String(repeating: "0", count: 9))
        let request = app.textViews["setup.request"].firstMatch.exists
            ? app.textViews["setup.request"].firstMatch : app.textFields["setup.request"].firstMatch
        request.tap()
        request.typeText("Book a check-up tomorrow morning.")
        app.buttons["setup.call"].tap()
        let receptionist = app.staticTexts.matching(NSPredicate(format: "label CONTAINS[c] %@", "hello passport office")).firstMatch
        XCTAssertTrue(receptionist.waitForExistence(timeout: 25), "real backend captions must reach the native screen")
        let field = app.textFields["steer.field"].firstMatch.exists
            ? app.textFields["steer.field"].firstMatch : app.textViews["steer.field"].firstMatch
        field.tap()
        field.typeText("Please wait a moment.")
        app.buttons["steer.send"].tap()
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS[c] %@", "Please wait a moment")).firstMatch.waitForExistence(timeout: 12))
        let end = app.buttons["steer.end"]
        if end.exists { end.tap() }
        let outcome = app.staticTexts["notes.outcome"].firstMatch
        XCTAssertTrue(outcome.waitForExistence(timeout: 15) || app.otherElements["notes.outcome"].waitForExistence(timeout: 2), "the gist must use the same placed call")
        attach("native-backend-gist")
    }

    func testBackendStatusLivesInSettingsAndTheAppStaysPortrait() throws {
        try XCTSkipUnless(ProcessInfo.processInfo.environment["ISHARA_LOCAL_BACKEND"] == "1")
        app.terminate()
        app.launchArguments = ["-IsharaCallHistory", "memory", "-IsharaFlow", "steer", "-IsharaDriver", "live", "-IsharaRecognition", "scripted"]
        app.launch()
        XCTAssertTrue(app.buttons["setup.settings"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["setup.backendStatus"].exists)
        XCTAssertFalse(app.buttons["settings.backendStatus"].exists)
        app.buttons["setup.settings"].tap()
        let status = app.buttons["settings.backendStatus"]
        XCTAssertTrue(status.waitForExistence(timeout: 5))
        status.tap()
        XCTAssertTrue(app.buttons["Check again"].waitForExistence(timeout: 5))
        app.buttons["Done"].firstMatch.tap()
        app.buttons["settings.done"].tap()
        XCTAssertTrue(app.textFields["setup.number"].firstMatch.waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["settings.backendStatus"].exists)
        defer { XCUIDevice.shared.orientation = .portrait }
        XCUIDevice.shared.orientation = .landscapeLeft
        XCTAssertLessThan(app.frame.width, app.frame.height, "The app remains portrait when the phone rotates")
    }

    private func attach(_ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
