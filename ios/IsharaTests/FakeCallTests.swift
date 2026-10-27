import CallSession
import XCTest
@testable import Ishara

/// The fake demo call and the scripted recognizer, run headless at high speed.
@MainActor
final class FakeCallTests: XCTestCase {
    private let fast = 0.01

    func testTheWholeClinicScriptPlaysThroughTheRealTurnRules() async throws {
        let recognition = ScriptedRecognitionController(timeScale: fast)
        let driver = FakeCallDriver(
            options: .init(timeScale: fast, undeliveredStages: [1]), recognition: recognition)
        let model = ActiveCallViewModel(setup: .demo, driver: driver, recognition: recognition)
        let run = Task { await model.run() }
        defer { run.cancel() }

        // Turn 1: hello · doctor · tomorrow → LLM draft → SEND → delivered.
        let firstDraft = await eventually(timeout: .seconds(5)) {
            model.draft?.text == "Hello, I'd like a doctor's appointment tomorrow."
        }
        XCTAssertTrue(firstDraft)
        XCTAssertEqual(model.captions.first, Caption(text: DemoScript.disclosure,
                                                     at: try XCTUnwrap(model.captions.first).at, speaker: .agent),
                       "the call opens with the agent's disclosure")
        model.send()
        let firstDelivered = await eventually(timeout: .seconds(5)) { model.delivery == .delivered }
        XCTAssertTrue(firstDelivered)

        // Turns 2–3b: the planned wrong chip is removed, then the reply isn't delivered once.
        let wrongChip = await eventually(timeout: .seconds(5)) {
            model.chips.compactMap(\.sign) == [.no, .afternoon, .morning]
        }
        XCTAssertTrue(wrongChip)
        XCTAssertEqual(model.captions.last?.text, "We have 4 pm tomorrow. Does that work?")
        model.removeChip(try XCTUnwrap(model.chips.first { $0.sign == .afternoon }))
        let secondDraft = await eventually(timeout: .seconds(5)) { model.draft?.badge == .llm }
        XCTAssertTrue(secondDraft)
        model.send()
        let notDelivered = await eventually(timeout: .seconds(5)) {
            model.delivery == .notDelivered(text: "No, sorry, 4 pm doesn't work. Is there anything tomorrow morning?")
        }
        XCTAssertTrue(notDelivered)
        model.send()
        let retried = await eventually(timeout: .seconds(5)) { model.delivery == .delivered }
        XCTAssertTrue(retried)

        // Turns 4–5: the unsure sign shows as [?] and is never part of the draft.
        let lastChips = await eventually(timeout: .seconds(5)) {
            model.chips.map(\.label) == ["yes", "?", "thankyou"]
        }
        XCTAssertTrue(lastChips)
        let lastDraft = await eventually(timeout: .seconds(5)) {
            model.draft?.text == "Yes, 10:30 tomorrow morning works. Thank you."
        }
        XCTAssertTrue(lastDraft)
        model.send()
        let done = await eventually(timeout: .seconds(5)) { model.delivery == .delivered }
        XCTAssertTrue(done)

        XCTAssertEqual(model.captions.filter { $0.speaker == .user }.map(\.text), [
            "Hello, I'd like a doctor's appointment tomorrow.",
            "No, sorry, 4 pm doesn't work. Is there anything tomorrow morning?",
            "Yes, 10:30 tomorrow morning works. Thank you.",
        ])
        model.end()
        XCTAssertEqual(model.phase, .ended(.userEnded))
        XCTAssertEqual(model.captions.last?.text, DemoScript.goodbye)
        XCTAssertEqual(model.captions.last?.speaker, .agent)
        XCTAssertEqual(model.captions.filter { $0.speaker == .agent }.count, 2, "only the disclosure and the goodbye")
    }

    /// Like the backend (`draft_is_current`), the fake never sends a draft for chips that have
    /// since changed. On a busy simulator two signs landed inside one draft delay, their drafts
    /// came back in the wrong order and the older one stayed on screen (issue #31).
    func testADraftForChipsThatHaveSinceChangedIsNeverSent() async throws {
        // Drafts come 1 s after their chips; the chips change again halfway through.
        let driver = FakeCallDriver(options: .init(timeScale: 2))
        let store = try await driver.start(.demo)
        defer { driver.close() }
        let current = "Hello, I'd like a doctor's appointment tomorrow."
        store.add(.recognised(.hello))
        store.add(.recognised(.doctor))
        try await Task.sleep(for: .milliseconds(500))
        store.add(.recognised(.tomorrow))

        // The drafts for the old chips were due at 1 s, the current one at 1.5 s.
        try await Task.sleep(for: .milliseconds(750))
        XCTAssertTrue(store.draft == nil || store.draft?.text == current,
                      "a draft for the old chips was shown: \(store.draft?.text ?? "")")
        let shown = await eventually(timeout: .seconds(5)) { store.draft?.text == current }
        XCTAssertTrue(shown)
    }

    // MARK: Scripted recognition

    func testReplayedSignShowsTheYellowPillThenTheResult() async {
        let recognition = ScriptedRecognitionController(offersReplay: true, timeScale: fast)
        var events: [RecognitionEvent] = []
        let stream = recognition.signingEvents()
        let listener = Task { for await event in stream { events.append(event) } }
        defer { listener.cancel() }

        recognition.replay("hello")
        let first = await eventually { events.count == 3 }
        recognition.replay(ScriptedRecognitionController.unsureOption)
        let second = await eventually { events.count == 6 }

        XCTAssertTrue(first && second)
        XCTAssertEqual(events.filter { if case .result = $0 { true } else { false } },
                       [.result(.sign(.hello)), .result(.unsure)])
        XCTAssertEqual(events.first, .camera(.signing))
        XCTAssertEqual(events.last, .camera(.watching))
        XCTAssertEqual(recognition.replayOptions.count, Sign.allCases.count + 2 + Sign.rehearsed.count,
                       "every sign, ?, frame, and a candidate per rehearsed sign")
    }

    func testReplayMenuOffersCandidatesAndTheFramingCase() async {
        let recognition = ScriptedRecognitionController(offersReplay: true, timeScale: fast)
        var results: [RecognitionResult] = []
        let listener = Task {
            for await event in recognition.signingEvents() {
                if case .result(let result) = event { results.append(result) }
            }
        }
        defer { listener.cancel() }

        recognition.replay("tomorrow?")
        recognition.replay(ScriptedRecognitionController.framingOption)

        let played = await eventually { results.count == 2 }
        XCTAssertTrue(played)
        XCTAssertTrue(results.contains(.candidate(.tomorrow)))
        XCTAssertTrue(results.contains(.handLeftFrame))
        XCTAssertTrue(recognition.replayOptions.contains("tomorrow?"))
    }

    // MARK: Delegated call (D9)

    private func delegatedSetup(attended: Bool) -> CallSetup {
        var setup = CallSetup.demo
        let request = BriefRequest(purpose: .doctorAppointment, chips: [.tomorrow, .morning], profile: Profile(name: "Riya"))
        setup.delegation = Delegation(brief: DelegatedDemo.brief(for: request), attended: attended)
        return setup
    }

    func testAttendedDelegatedCallAsksThenBooksOnYes() async throws {
        let driver = FakeCallDriver(options: .init(timeScale: fast))
        let model = ActiveCallViewModel(setup: delegatedSetup(attended: true), driver: driver, recognition: StubRecognition())
        let run = Task { await model.run() }
        defer { run.cancel() }

        let asked = await eventually(timeout: .seconds(5)) { model.openQuestion != nil }
        XCTAssertTrue(asked)
        XCTAssertEqual(model.openQuestion?.question, DelegatedDemo.offer)
        XCTAssertEqual(model.captions.map(\.text).prefix(2), [
            DemoScript.disclosure, "I'd like to book a doctor's appointment for Riya, tomorrow in the morning.",
        ])

        model.handle(.result(.sign(.yes)))

        let ended = await eventually(timeout: .seconds(5)) { model.isEnded }
        XCTAssertTrue(ended)
        XCTAssertNil(model.openQuestion)
        XCTAssertTrue(model.chips.isEmpty, "a delegated call never composes chips")
        let notes = try await driver.notes()
        XCTAssertTrue(notes.ready)
        XCTAssertEqual(notes.mode, .delegated)
        XCTAssertEqual(notes.outcome, "booked")
        XCTAssertTrue(notes.summary.contains("You answered: \"Yes, 10:30 tomorrow works. Thank you.\""))
        XCTAssertEqual(notes.transcript.last?.text, DelegatedDemo.closeLine)
    }

    func testUnattendedDelegatedCallPromisesACallbackAndNeverAsks() async throws {
        let driver = FakeCallDriver(options: .init(timeScale: fast))
        let model = ActiveCallViewModel(setup: delegatedSetup(attended: false), driver: driver, recognition: StubRecognition())
        let run = Task { await model.run() }
        defer { run.cancel() }

        let ended = await eventually(timeout: .seconds(5)) { model.isEnded }
        XCTAssertTrue(ended)
        XCTAssertTrue(model.captions.contains { $0.text == DelegatedDemo.callbackLine })
        let notes = try await driver.notes()
        XCTAssertEqual(notes.outcome, "callback")
        XCTAssertEqual(notes.openQuestions.count, 1)
    }

    func testUnansweredQuestionTimesOutToTheCallbackLine() async throws {
        let driver = FakeCallDriver(options: .init(timeScale: fast))
        let model = ActiveCallViewModel(setup: delegatedSetup(attended: true), driver: driver, recognition: StubRecognition())
        let run = Task { await model.run() }
        defer { run.cancel() }

        let ended = await eventually(timeout: .seconds(5)) { model.isEnded }
        XCTAssertTrue(ended)
        let notes = try await driver.notes()
        XCTAssertEqual(notes.outcome, "callback")
        XCTAssertTrue(model.captions.contains { $0.text == DelegatedDemo.callbackLine })
    }

    func testWaitKeepsTheQuestionOpen() async {
        let driver = FakeCallDriver(options: .init(timeScale: fast))
        let model = ActiveCallViewModel(setup: delegatedSetup(attended: true), driver: driver, recognition: StubRecognition())
        let run = Task { await model.run() }
        defer { run.cancel() }
        let asked = await eventually(timeout: .seconds(5)) { model.openQuestion != nil }
        XCTAssertTrue(asked)

        model.answer(.wait)

        XCTAssertNotNil(model.openQuestion, "wait holds the line; the question stays")
        XCTAssertEqual(model.captions.last?.text, "One moment, please, I'm checking.")
        driver.close()
    }

    func testFakeBriefSaysOnlyWhatWasSignedAndTyped() async throws {
        let driver = FakeCallDriver()
        let brief = try await driver.createBrief(BriefRequest(
            purpose: .doctorAppointment, chips: [.now, .afternoon], profile: Profile(name: " Riya ", callback: "123")))

        XCTAssertEqual(brief.text, "Call on behalf of Riya, who is Deaf and uses the Ishara app, to book a doctor's appointment. "
            + "Preferred: today in the afternoon. May share: name (Riya), callback number. "
            + "Will not agree to anything outside this brief; anything else comes back to you as a question.")
        XCTAssertEqual(brief.constraints, ["preferred time: today in the afternoon"])
    }

    func testScriptPlaysOnceSigningStarts() async {
        let recognition = ScriptedRecognitionController(script: [.sign(.yes), .unsure], timeScale: fast)
        var results: [RecognitionResult] = []
        let listener = Task {
            for await event in recognition.signingEvents() {
                if case .result(let result) = event { results.append(result) }
            }
        }
        defer { listener.cancel() }

        let played = await eventually { results == [.sign(.yes), .unsure] }
        XCTAssertTrue(played)
    }

    func testGetReadyTicksOnTimersWhenReplayingFixedResults() async {
        let recognition = ScriptedRecognitionController(timeScale: fast)

        recognition.start()

        let ready = await eventually { recognition.getReady.isReady }
        XCTAssertTrue(ready)
        XCTAssertTrue(recognition.replayOptions.isEmpty)
    }
}
