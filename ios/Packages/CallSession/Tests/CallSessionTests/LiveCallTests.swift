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

        let sent = await eventually { await self.transport.sent.count == 1 }
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
