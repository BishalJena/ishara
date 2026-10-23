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
        XCTAssertEqual(body, #"{"contact_id":"clinic","purpose":"doctor_appointment"}"#)
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
        let offered = await eventually { model.delivery == .notDelivered(text: "Hello.") }
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
        XCTAssertEqual(model.phase, .interrupted("Nothing will be sent"))
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
