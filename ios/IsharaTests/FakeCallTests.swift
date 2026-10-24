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
        XCTAssertEqual(recognition.replayOptions.count, 13, "12 signs and ?")
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
