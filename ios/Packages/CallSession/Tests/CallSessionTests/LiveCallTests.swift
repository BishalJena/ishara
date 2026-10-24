import XCTest

@testable import CallSession

@MainActor
final class LiveCallTests: XCTestCase {
    private var http: FakeHTTP!
    private var transport: FakeTransport!
    private var client: BackendClient!

    override func setUp() async throws {
        http = FakeHTTP()
        transport = FakeTransport()
        client = BackendClient(config: testConfig, http: http, transport: transport)
    }

    private func startCall() async throws -> LiveCall {
        let ids = SequentialTurnIDs()
        return try await LiveCall.start(
            client: client, contactID: "city_clinic", purpose: .doctorAppointment,
            makeTurnID: { ids.make() })
    }

    func testStartPlacesTheCallThenOpensItsSocket() async throws {
        let call = try await startCall()

        XCTAssertEqual(call.callID, "call_123")
        XCTAssertEqual(call.store.state, .dialing)
        let requests = await transport.requests
        XCTAssertEqual(requests.map(\.url?.absoluteString), ["wss://backend.example.test/calls/call_123/ws"])
    }

    func testFailedStartOpensNoSocket() async {
        client = BackendClient(
            config: testConfig, http: FakeHTTP(status: 401, body: "{}"), transport: transport)
        do {
            _ = try await startCall()
            XCTFail("a rejected call must throw")
        } catch {
            XCTAssertEqual(error as? BackendError, .httpStatus(401))
        }
        let requests = await transport.requests
        XCTAssertEqual(requests, [])
    }

    func testSocketEventsReachTheStoreAndSendGoesOnTheWire() async throws {
        let call = try await startCall()
        let store = call.store

        await transport.push(#"{"type":"status","state":"in_call"}"#)
        let live = await eventually { @MainActor in store.state == .inCall }
        XCTAssertTrue(live)
        store.useQuickReply(.yes)
        store.send()

        let transport = transport!
        let sent = await eventually { await transport.sent.count == 1 }
        XCTAssertTrue(sent)
        let frames = await transport.sent
        XCTAssertEqual(frames, [#"{"text":"Yes.","turn_id":"turn2","type":"approve"}"#])
    }

    func testDroppedSocketSilencesTheStore() async throws {
        let call = try await startCall()
        let store = call.store

        await transport.drop()

        let silent = await eventually { @MainActor in store.state == .error }
        XCTAssertTrue(silent)
        XCTAssertEqual(store.notice, TurnStore.disconnectedNotice)
    }

    func testDroppedSocketIsReportedToTheOwner() async throws {
        let call = try await startCall()
        var reports = 0
        call.onConnectionLost = { reports += 1 }

        await transport.drop()

        let reported = await eventually { @MainActor in reports == 1 }
        XCTAssertTrue(reported)
    }

    func testEndedCallClosingItsSocketIsNotReported() async throws {
        let call = try await startCall()
        var reports = 0
        call.onConnectionLost = { reports += 1 }
        await transport.push(#"{"type":"status","state":"ended"}"#)
        _ = await eventually { @MainActor in call.store.state == .ended }

        await transport.drop()
        try? await Task.sleep(for: .milliseconds(50))

        XCTAssertEqual(reports, 0)
    }

    func testReplacingTheSocketIsNotReported() async throws {
        let call = try await startCall()
        var reports = 0
        call.onConnectionLost = { reports += 1 }

        await call.connect()
        try? await Task.sleep(for: .milliseconds(50))

        XCTAssertEqual(reports, 0)
    }

    func testFailedSendSilencesTheStore() async throws {
        let call = try await startCall()
        let store = call.store
        await transport.setFailSends(true)

        store.add(.recognised(.hello))

        let silent = await eventually { @MainActor in store.state == .error }
        XCTAssertTrue(silent)
    }

    func testReconnectSendsNothingOldAndRecoversOnStatus() async throws {
        let call = try await startCall()
        let store = call.store
        await transport.push(#"{"type":"status","state":"in_call"}"#)
        _ = await eventually { @MainActor in store.state == .inCall }
        store.useQuickReply(.yes)
        await transport.drop()
        _ = await eventually { @MainActor in store.state == .error }

        await call.connect()
        await transport.push(#"{"type":"status","state":"in_call"}"#)

        let recovered = await eventually { @MainActor in store.state == .inCall }
        XCTAssertTrue(recovered)
        try? await Task.sleep(for: .milliseconds(50))
        XCTAssertEqual(store.state, .inCall, "replacing the socket must not report a disconnect")
        XCTAssertNil(store.draft)
        let requests = await transport.requests
        XCTAssertEqual(requests.count, 2)
        let frames = await transport.sent
        XCTAssertEqual(frames, [], "nothing from before the drop is sent")
    }

    func testRefusedOrReplacedSocketIsNotReopened() async throws {
        let cases: [(Int, CallSocketClose)] = [
            (4401, .unauthorized), (4404, .unknownCall), (4409, .replaced),
        ]
        for (code, expected) in cases {
            transport = FakeTransport()
            client = BackendClient(config: testConfig, http: http, transport: transport)
            let call = try await startCall()
            let store = call.store

            await transport.drop(code: code)
            _ = await eventually { @MainActor in store.state == .error }
            await call.connect()

            let close = await call.lastClose
            XCTAssertEqual(close, expected, "code \(code)")
            let requests = await transport.requests
            XCTAssertEqual(requests.count, 1, "code \(code) must not open another socket")
            XCTAssertEqual(store.state, .error)
            XCTAssertEqual(store.notice, TurnStore.disconnectedNotice)
        }
    }

    func testPlainDropIsReopened() async throws {
        let call = try await startCall()
        let store = call.store

        await transport.drop(code: 1006)
        _ = await eventually { @MainActor in store.state == .error }
        await call.connect()

        let close = await call.lastClose
        XCTAssertNil(close, "the reopened socket is live")
        let requests = await transport.requests
        XCTAssertEqual(requests.count, 2)
    }

    func testReplacingALiveSocketIsNotADisconnect() async throws {
        let call = try await startCall()
        let store = call.store
        await transport.push(#"{"type":"status","state":"in_call"}"#)
        _ = await eventually { @MainActor in store.state == .inCall }

        await call.connect()
        try? await Task.sleep(for: .milliseconds(50))

        XCTAssertEqual(store.state, .inCall)
        XCTAssertNil(store.notice)
        let requests = await transport.requests
        XCTAssertEqual(requests.count, 2)
    }
}
