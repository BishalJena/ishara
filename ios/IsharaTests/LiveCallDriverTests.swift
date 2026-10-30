import CallSession
import XCTest
@testable import Ishara

/// The real driver against an in-memory backend: HTTP for `POST /calls`, a fake socket for
/// the call. Checks the screens' view model end to end through CallSession.
@MainActor
final class LiveCallDriverTests: XCTestCase {
    private var http: FakeHTTP!
    private var transport: FakeTransport!
    private var ids: SequentialTurnIDs!

    override func setUp() async throws {
        http = FakeHTTP()
        transport = FakeTransport()
        ids = SequentialTurnIDs()
    }

    private func makeDriver(http: FakeHTTP? = nil, reconnectDelays: [Duration] = [.zero, .zero]) -> LiveCallDriver {
        let ids = ids!
        return LiveCallDriver(
            client: BackendClient(config: testBackend, http: http ?? self.http, transport: transport),
            reconnectDelays: reconnectDelays,
            sleep: { _ in },
            makeTurnID: { ids.make() })
    }

    private func makeModel(_ driver: LiveCallDriver) -> ActiveCallViewModel {
        ActiveCallViewModel(setup: .demo, driver: driver, recognition: StubRecognition())
    }

    private func sentFrames() async -> [String] { await transport.sent }

    private func waitForFrames(_ count: Int) async -> Bool {
        await eventually { await self.transport.sent.count >= count }
    }

    // MARK: Starting

    func testStartAsksTheBackendForTheChosenContactThenOpensTheCallSocket() async throws {
        let model = makeModel(makeDriver())

        await model.start()

        let requests = await http.requests
        XCTAssertEqual(requests.map(\.url?.absoluteString), ["https://backend.example.test/calls"])
        XCTAssertEqual(requests.first?.value(forHTTPHeaderField: "Authorization"), "Bearer test-token")
        let body = try XCTUnwrap(requests.first?.httpBody.map { String(decoding: $0, as: UTF8.self) })
        XCTAssertEqual(body, #"{"attended":false,"contact_id":"clinic","mode":"live","purpose":"doctor_appointment"}"#)
        let sockets = await transport.requests
        XCTAssertEqual(sockets.map(\.url?.absoluteString), ["wss://backend.example.test/calls/call_1/ws"])
        XCTAssertEqual(sockets.first?.value(forHTTPHeaderField: "Authorization"), "Bearer test-token")
        XCTAssertEqual(model.phase, .connecting(.dialing))
    }

    func testRefusedStartShowsWhyAndOpensNoSocket() async {
        let model = makeModel(makeDriver(http: FakeHTTP(status: 401, body: "{}")))

        await model.start()

        XCTAssertEqual(model.phase, .ended(.failed("The app token was refused. Check the app configuration.")))
        let sockets = await transport.requests
        XCTAssertEqual(sockets, [])
    }

    // MARK: A whole turn

    func testScreensFollowTheBackendAndEveryTapGoesOnTheWire() async throws {
        let model = makeModel(makeDriver())
        await model.start()

        await transport.push(#"{"type":"status","state":"in_call"}"#)
        await transport.push(#"{"type":"caption","text":"City Clinic, how can I help?","at":1}"#)
        let live = await eventually { model.phase == .live && model.captions.count == 1 }
        XCTAssertTrue(live)

        model.handle(.result(.sign(.hello)))
        model.handle(.result(.unsure))
        let sent1 = await waitForFrames(1)
        XCTAssertTrue(sent1)
        await transport.push(#"{"type":"draft","turn_id":"turn1","text":"Hello.","source":"llm"}"#)
        let drafted = await eventually { model.draft == DraftDisplay(text: "Hello.", badge: .llm) }
        XCTAssertTrue(drafted)

        model.send()
        await transport.push(#"{"type":"status","state":"speaking"}"#)
        _ = await eventually { model.isSpeaking }
        model.stop()
        let sent2 = await waitForFrames(3)
        XCTAssertTrue(sent2)
        await transport.push(#"{"type":"not_delivered","turn_id":"turn1","reason":"stopped"}"#)
        let offered = await eventually { model.delivery == .stopped(text: "Hello.") }
        XCTAssertTrue(offered)

        model.send()
        let sent3 = await waitForFrames(4)
        XCTAssertTrue(sent3)
        await transport.push(#"{"type":"spoken","turn_id":"turn3"}"#)
        let delivered = await eventually { model.delivery == .delivered }
        XCTAssertTrue(delivered)
        XCTAssertEqual(model.captions.map(\.speaker), [.receptionist, .user])

        model.end()
        let sent4 = await waitForFrames(5)
        XCTAssertTrue(sent4)
        XCTAssertEqual(model.phase, .ended(.userEnded))

        let frames = await sentFrames()
        XCTAssertEqual(frames, [
            #"{"chips":["hello"],"turn_id":"turn1","type":"chips"}"#,
            #"{"text":"Hello.","turn_id":"turn1","type":"approve"}"#,
            #"{"type":"stop"}"#,
            #"{"text":"Hello.","turn_id":"turn3","type":"approve"}"#,
            #"{"type":"end"}"#,
        ])
    }

    func testRemoteHangUpEndsTheScreen() async {
        let model = makeModel(makeDriver())
        await model.start()

        await transport.push(#"{"type":"status","state":"ended"}"#)

        let ended = await eventually { model.phase == .ended(.remoteEnded) }
        XCTAssertTrue(ended)
    }

    // MARK: Disconnects

    func testDroppedSocketReconnectsAndResendsNothing() async {
        let model = makeModel(makeDriver())
        await model.start()
        await transport.push(#"{"type":"status","state":"in_call"}"#)
        _ = await eventually { model.phase == .live }
        model.choose(.yes)

        await transport.drop()

        let reconnected = await eventually { await self.transport.requests.count == 2 }
        XCTAssertTrue(reconnected)
        XCTAssertEqual(model.phase, .interrupted("Nothing will be sent"))
        XCTAssertNil(model.draft, "the draft was wiped")
        await transport.push(#"{"type":"status","state":"in_call"}"#)
        let recovered = await eventually { model.phase == .live }
        XCTAssertTrue(recovered)
        let frames = await sentFrames()
        XCTAssertEqual(frames, [], "nothing from before the drop is sent")
    }

    func testReconnectsStopAfterTheLastScheduledAttempt() async {
        let model = makeModel(makeDriver(reconnectDelays: [.zero, .zero]))
        await model.start()

        for attempt in 1...3 {
            _ = await eventually { await self.transport.requests.count == attempt }
            await transport.drop()
        }
        try? await Task.sleep(for: .milliseconds(100))

        let sockets = await transport.requests
        XCTAssertEqual(sockets.count, 3, "the first socket plus two reconnects")
        let gaveUp = await eventually { model.phase == .disconnected("The connection couldn't be restored") }
        XCTAssertTrue(gaveUp, "still promising a reconnect: \(model.phase)")
    }

    func testRefusedSocketIsNeverReopenedAndTheScreenSaysWhy() async {
        let refusals: [(code: Int, reason: String)] = [
            (4401, "The backend refused the app token"),
            (4404, "The backend no longer knows this call"),
            (4409, "This call is now connected somewhere else"),
        ]
        for refusal in refusals {
            transport = FakeTransport()
            let model = makeModel(makeDriver())
            await model.start()
            await transport.push(#"{"type":"status","state":"in_call"}"#)
            _ = await eventually { model.phase == .live }

            await transport.drop(code: refusal.code)

            let explained = await eventually { model.phase == .disconnected(refusal.reason) }
            XCTAssertTrue(explained, "\(refusal.code): \(model.phase)")
            try? await Task.sleep(for: .milliseconds(50))
            let sockets = await transport.requests
            XCTAssertEqual(sockets.count, 1, "\(refusal.code) was reconnected")
            XCTAssertFalse(model.isEnded, "End stays available")
        }
    }

    func testDropWithAnOrdinaryCloseCodeStillReconnects() async {
        let model = makeModel(makeDriver())
        await model.start()

        await transport.drop(code: 1001)

        let reconnected = await eventually { await self.transport.requests.count == 2 }
        XCTAssertTrue(reconnected)
        XCTAssertEqual(model.phase, .interrupted("Nothing will be sent"))
    }

    // MARK: Delegated call (D9)

    func testDelegatedFlowBuildsTheBriefStartsWithItAndFetchesTheNotes() async throws {
        let http = FakeHTTP(routes: [
            "/briefs": #"{"brief_id":"b7","text":"Call on behalf of Riya.","goal":"book a doctor's appointment","constraints":[]}"#,
            "/calls": #"{"call_id":"call_9","state":"dialing","mode":"delegated"}"#,
            "/calls/call_9/notes": #"{"call_id":"call_9","mode":"delegated","ready":true,"brief":"Call on behalf of Riya.","outcome":"booked","summary":["Goal: book a doctor's appointment for Riya."],"open_questions":[],"transcript":[{"speaker":"receptionist","text":"Booked.","at":1}],"bolna_summary":null}"#,
        ])
        let driver = makeDriver(http: http)

        let brief = try await driver.createBrief(BriefRequest(
            purpose: .doctorAppointment, chips: [.tomorrow], profile: Profile(name: "Riya")))
        var setup = CallSetup.demo
        setup.delegation = Delegation(brief: brief, attended: true)
        let model = ActiveCallViewModel(setup: setup, driver: driver, recognition: StubRecognition())
        await model.start()
        model.leave()
        let notes = try await driver.notes()

        let requests = await http.requests
        XCTAssertEqual(requests.map(\.url?.path), ["/briefs", "/calls", "/calls/call_9/notes"])
        XCTAssertEqual(requests.map(\.httpMethod), ["POST", "POST", "GET"])
        let briefBody = try XCTUnwrap(requests[0].httpBody.map { String(decoding: $0, as: UTF8.self) })
        XCTAssertEqual(briefBody, #"{"chips":["tomorrow"],"profile":{"details":[],"name":"Riya"},"purpose":"doctor_appointment"}"#)
        let startBody = try XCTUnwrap(requests[1].httpBody.map { String(decoding: $0, as: UTF8.self) })
        XCTAssertEqual(startBody,
                       #"{"attended":true,"brief_id":"b7","contact_id":"clinic","mode":"delegated","purpose":"doctor_appointment"}"#)
        XCTAssertEqual(notes.outcome, "booked")
        XCTAssertEqual(notes.transcript.first?.text, "Booked.")
    }

    func testNotesBeforeAnyCallIsAnError() async {
        do {
            _ = try await makeDriver().notes()
            XCTFail("expected an error")
        } catch {
            XCTAssertEqual(error as? CallDriverError, .noCall)
        }
    }

    func testCloseDisconnectsAndStopsReconnecting() async {
        let driver = makeDriver()
        let model = makeModel(driver)
        await model.start()

        model.leave()
        let closed = await eventually { await self.transport.closeCount == 1 }
        XCTAssertTrue(closed)
        try? await Task.sleep(for: .milliseconds(50))

        let sockets = await transport.requests
        XCTAssertEqual(sockets.count, 1)
    }
}
