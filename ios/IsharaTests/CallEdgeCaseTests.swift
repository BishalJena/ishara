import CallSession
import XCTest
@testable import Ishara

/// Call edge cases at the view-model level, headless and fast: a lost connection mid-call
/// (live and delegated) and a receptionist talking over the reply. The UI tests in
/// `CallEdgeCaseUITests` / `DelegatedEdgeCaseUITests` walk the same cases on screen.
@MainActor
final class CallEdgeCaseTests: XCTestCase {
    /// Fast, but slow enough that a state lasting one script step (the open question before
    /// the drop, the draft before it) is still seen by `eventually`'s 5 ms polls.
    private let fast = 0.05
    private let turn1 = "Hello, I'd like a doctor's appointment tomorrow."

    private func delegatedSetup() -> CallSetup {
        var setup = CallSetup.demo
        let request = BriefRequest(purpose: .doctorAppointment, chips: [.tomorrow, .morning], profile: Profile(name: "Riya"))
        setup.delegation = Delegation(brief: DelegatedDemo.brief(for: request), attended: true)
        return setup
    }

    // MARK: Launch switches

    func testLaunchSwitchesTurnOnTheFakeCallsEdgeCases() throws {
        let suite = "CallEdgeCaseTests.launchSwitches"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        XCTAssertNil(DemoLaunchOptions.from(defaults).fakeDriverOptions.connectionDrop)
        XCTAssertEqual(DemoLaunchOptions.from(defaults).fakeDriverOptions.interruptedStages, [])

        defaults.set(true, forKey: "IsharaFakeInterrupt")
        defaults.set("staysDown", forKey: "IsharaFakeConnectionDrop")
        let options = DemoLaunchOptions.from(defaults).fakeDriverOptions

        XCTAssertEqual(options.interruptedStages, [0])
        XCTAssertEqual(options.connectionDrop, .staysDown)
        defaults.set("reconnects", forKey: "IsharaFakeConnectionDrop")
        XCTAssertEqual(DemoLaunchOptions.from(defaults).fakeDriverOptions.connectionDrop, .reconnects)
    }

    // MARK: Lost connection, delegated (D9)

    /// Regression: the agent's question stayed on screen and answerable after the
    /// connection dropped, so a tap went into a dead socket (or, after a reconnect, to a
    /// question the backend had already resolved).
    func testLostConnectionWipesTheAgentsQuestion() async {
        let driver = StubCallDriver()
        let model = ActiveCallViewModel(setup: delegatedSetup(), driver: driver, recognition: StubRecognition())
        await model.start()
        driver.store.receive(.status(.inCall))
        driver.store.receive(.ask(
            askID: "a1", question: DelegatedDemo.offer, options: DelegatedDemo.options,
            fallback: DelegatedDemo.callbackLine, timeoutS: 10))
        XCTAssertNotNil(model.openQuestion)

        driver.store.connectionLost()

        XCTAssertNil(model.openQuestion, "the question outlived the connection")
        model.answer(.yes)
        model.handle(.result(.sign(.yes)))
        XCTAssertEqual(driver.sink.sent, [], "an answer went out with the connection gone")
    }

    func testFakeConnectionThatStaysDownEndsReconnectingAndFailsTheNotes() async {
        let driver = FakeCallDriver(options: .init(timeScale: fast, connectionDrop: .staysDown))
        let model = ActiveCallViewModel(setup: delegatedSetup(), driver: driver, recognition: StubRecognition())
        let run = Task { await model.run() }
        defer { run.cancel() }

        let asked = await eventually(timeout: .seconds(5)) { model.openQuestion != nil }
        XCTAssertTrue(asked)
        let dropped = await eventually(timeout: .seconds(5)) { model.phase == .interrupted(TurnStore.disconnectedNotice) }
        XCTAssertTrue(dropped)
        XCTAssertNil(model.openQuestion)
        let gaveUp = await eventually(timeout: .seconds(5)) { model.reconnectStop == .attemptsUsedUp }
        XCTAssertTrue(gaveUp)
        XCTAssertTrue(model.isCallOver)

        model.leave()
        let notes = NotesModel(contactName: "City Clinic", driver: driver)
        await notes.refresh()
        XCTAssertNil(notes.notes)
        XCTAssertEqual(notes.failure, "The notes couldn't be loaded: \(URLError(.cannotConnectToHost).localizedDescription)")
    }

    // MARK: Lost connection, live

    func testFakeDropWipesTheDraftAndTheReconnectResendsNothing() async {
        let recognition = ScriptedRecognitionController(timeScale: fast)
        let driver = FakeCallDriver(options: .init(timeScale: fast, connectionDrop: .reconnects), recognition: recognition)
        let model = ActiveCallViewModel(setup: .demo, driver: driver, recognition: recognition)
        let run = Task { await model.run() }
        defer { run.cancel() }

        let drafted = await eventually(timeout: .seconds(5)) { model.draft?.text == turn1 }
        XCTAssertTrue(drafted)
        let dropped = await eventually(timeout: .seconds(5)) { model.phase == .interrupted(TurnStore.disconnectedNotice) }
        XCTAssertTrue(dropped)
        XCTAssertNil(model.draft)
        XCTAssertTrue(model.chips.isEmpty)
        XCTAssertFalse(model.canSend)
        model.send()

        let back = await eventually(timeout: .seconds(5)) { model.phase == .live }
        XCTAssertTrue(back)
        XCTAssertNil(model.draft, "the old draft came back with the connection")
        XCTAssertFalse(model.canSend)
        XCTAssertEqual(model.delivery, .idle, "something was sent across the drop")
        XCTAssertFalse(model.captions.contains { $0.speaker == .user })
    }

    // MARK: Receptionist talks over the reply

    func testReceptionistTalkingOverTheReplyKeepsItSpeakingAndDelivers() async {
        let recognition = ScriptedRecognitionController(timeScale: fast)
        let driver = FakeCallDriver(options: .init(timeScale: fast, interruptedStages: [0]), recognition: recognition)
        let model = ActiveCallViewModel(setup: .demo, driver: driver, recognition: recognition)
        let run = Task { await model.run() }
        defer { run.cancel() }

        let drafted = await eventually(timeout: .seconds(5)) { model.draft?.text == turn1 }
        XCTAssertTrue(drafted)
        model.send()

        let interrupted = await eventually(timeout: .seconds(5)) {
            model.captions.last == Caption(text: FakeCallDriver.interruption, at: model.captions.last?.at ?? .now)
        }
        XCTAssertTrue(interrupted)
        XCTAssertEqual(model.delivery, .speaking(text: turn1), "the receptionist's words cut the reply off")
        let delivered = await eventually(timeout: .seconds(5)) { model.delivery == .delivered }
        XCTAssertTrue(delivered)
        XCTAssertEqual(model.captions.filter { $0.speaker == .user }.map(\.text), [turn1])
    }
}
