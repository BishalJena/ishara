import CallSession
import XCTest
@testable import Ishara

/// The call screen's D8 pick-one tile, the framing hint, and the delegated-call (D9) rules.
@MainActor
final class PickOneAndDelegatedTests: XCTestCase {
    private func liveModel() async -> (ActiveCallViewModel, StubCallDriver) {
        let driver = StubCallDriver()
        let model = ActiveCallViewModel(setup: .demo, driver: driver, recognition: StubRecognition())
        await model.start()
        driver.store.receive(.status(.inCall))
        return (model, driver)
    }

    private func delegatedModel(attended: Bool) async -> (ActiveCallViewModel, StubCallDriver) {
        var setup = CallSetup.demo
        setup.delegation = Delegation(
            brief: Brief(briefID: "b1", text: "…", goal: "book a doctor's appointment", constraints: []),
            attended: attended)
        let driver = StubCallDriver()
        let model = ActiveCallViewModel(setup: setup, driver: driver, recognition: StubRecognition())
        await model.start()
        driver.store.receive(.status(.inCall))
        return (model, driver)
    }

    private let question = ServerMessage.ask(
        askID: "a1", question: "We have 4 pm tomorrow. Does that work?",
        options: [AskOption(choice: .yes, spoken: "Yes."), AskOption(choice: .no, spoken: "No."),
                  AskOption(choice: .wait, spoken: "One moment.")],
        fallback: "I'll call back.", timeoutS: 10)

    // MARK: Pick-one (D8)

    func testCandidateIsOfferedButNeverAChipByItself() async {
        let (model, driver) = await liveModel()

        model.handle(.result(.candidate(.tomorrow)))

        XCTAssertEqual(model.candidate, .tomorrow)
        XCTAssertTrue(model.chips.isEmpty)
        XCTAssertEqual(driver.sink.sent, [], "nothing reaches the backend until the user taps")
    }

    func testTappingTheCandidateMakesItAChip() async {
        let (model, driver) = await liveModel()
        model.handle(.result(.candidate(.tomorrow)))

        model.acceptCandidate()

        XCTAssertNil(model.candidate)
        XCTAssertEqual(model.chips.map(\.label), ["tomorrow"])
        XCTAssertEqual(driver.sink.chipUpdates, [.chips(turnID: turn(1), chips: [.tomorrow])])
    }

    func testDismissingOrSigningAgainDropsTheCandidate() async {
        let (model, _) = await liveModel()
        model.handle(.result(.candidate(.tomorrow)))
        model.dismissCandidate()
        XCTAssertNil(model.candidate)

        model.handle(.result(.candidate(.morning)))
        model.handle(.result(.sign(.yes)))
        XCTAssertNil(model.candidate, "the next sign replaces the offer")
        XCTAssertEqual(model.chips.map(\.label), ["yes"])
    }

    func testCandidateGoesAwayWhenTheCallEnds() async {
        let (model, _) = await liveModel()
        model.handle(.result(.candidate(.tomorrow)))
        model.end()

        XCTAssertNil(model.candidate)
        model.acceptCandidate()
        XCTAssertTrue(model.chips.isEmpty)
    }

    // MARK: Framing

    func testHandLeavingTheFrameShowsTheHintAndAQuestionMark() async {
        let (model, driver) = await liveModel()

        model.handle(.result(.handLeftFrame))

        XCTAssertTrue(model.showsFramingHint)
        XCTAssertEqual(model.chips.map(\.label), ["?"])
        XCTAssertEqual(driver.sink.sent, [], "an unsure chip is never sent")
        model.handle(.result(.sign(.no)))
        XCTAssertFalse(model.showsFramingHint)
    }

    // MARK: Delegated call (D9)

    func testDelegatedCallNeverComposesChips() async {
        let (model, driver) = await delegatedModel(attended: true)

        model.handle(.result(.sign(.tomorrow)))
        model.handle(.result(.unsure))

        XCTAssertTrue(model.chips.isEmpty)
        XCTAssertEqual(driver.sink.sent, [])
    }

    func testSignedYesAnswersTheAgentsQuestion() async {
        let (model, driver) = await delegatedModel(attended: true)
        driver.store.receive(question)

        model.handle(.result(.sign(.yes)))

        XCTAssertEqual(driver.sink.sent, [.answer(askID: "a1", choice: .yes)])
    }

    func testTappedCandidateNoAnswersTheAgentsQuestion() async {
        let (model, driver) = await delegatedModel(attended: true)
        driver.store.receive(question)
        model.handle(.result(.candidate(.no)))
        XCTAssertEqual(driver.sink.sent, [], "a candidate alone answers nothing")

        model.acceptCandidate()

        XCTAssertEqual(driver.sink.sent, [.answer(askID: "a1", choice: .no)])
    }

    func testUnattendedCallIgnoresSigns() async {
        let (model, driver) = await delegatedModel(attended: false)
        driver.store.receive(question)

        model.handle(.result(.sign(.yes)))
        model.handle(.result(.candidate(.no)))

        XCTAssertFalse(model.watchesSigns)
        XCTAssertNil(model.candidate)
        XCTAssertEqual(driver.sink.sent, [])
    }

    func testDelegatedCallStartsWithItsBrief() async {
        let (model, driver) = await delegatedModel(attended: true)

        XCTAssertTrue(model.isDelegated)
        XCTAssertEqual(driver.startedWith.first?.startRequest.mode, .delegated)
        XCTAssertEqual(driver.startedWith.first?.startRequest.briefID, "b1")
        XCTAssertEqual(driver.startedWith.first?.startRequest.attended, true)
    }
}
