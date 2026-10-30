import XCTest

/// The steer flow on the fake driver: type the request, Call, watch Ishara's proposed line
/// fill and go out, step in by typing, see the typed line previewed and spoken, and
/// reach the gist. Nothing is dialled.
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
        XCTAssertTrue(app.staticTexts["Can we do 11 instead."].waitForExistence(timeout: 10), "the typed line is previewed, then shown as the user's")
        attach("typed")

        // The call runs to its end on its own; the gist is one tap away.
        let gist = app.buttons["steer.gist"]
        XCTAssertTrue(gist.waitForExistence(timeout: 60))
        gist.tap()
        XCTAssertTrue(app.staticTexts["notes.outcome"].waitForExistence(timeout: 10) || app.otherElements["notes.outcome"].waitForExistence(timeout: 2))
        attach("gist")
    }

    private func attach(_ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
