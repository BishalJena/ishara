import XCTest

@testable import CallSession

final class BackendClientTests: XCTestCase {
    // MARK: Config

    func testWebSocketBaseSwapsHTTPSForWSS() {
        let config = BackendConfig(baseURL: URL(string: "https://a.example.test/api")!, appToken: "x")
        XCTAssertEqual(config.webSocketBaseURL.absoluteString, "wss://a.example.test/api")
    }

    func testWebSocketBaseSwapsHTTPForWS() {
        let config = BackendConfig(baseURL: URL(string: "http://localhost:8000")!, appToken: "x")
        XCTAssertEqual(config.webSocketBaseURL.absoluteString, "ws://localhost:8000")
    }

    func testExplicitWebSocketBaseWins() {
        let config = BackendConfig(
            baseURL: URL(string: "https://a.example.test")!, appToken: "x",
            webSocketBaseURL: URL(string: "wss://b.example.test")!)
        XCTAssertEqual(config.webSocketBaseURL.absoluteString, "wss://b.example.test")
    }

    // MARK: REST

    func testStartCallPostsContractBodyWithBearerToken() async throws {
        let http = FakeHTTP()
        let client = BackendClient(config: testConfig, http: http, transport: FakeTransport())

        let start = try await client.startCall(contactID: "city_clinic", purpose: .doctorAppointment)

        XCTAssertEqual(start, CallStart(callID: "call_123", state: .dialing))
        let requests = await http.requests
        let request = try XCTUnwrap(requests.first)
        XCTAssertEqual(request.httpMethod, "POST")
        XCTAssertEqual(request.url?.absoluteString, "https://backend.example.test/calls")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer test-token")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Content-Type"), "application/json")
        XCTAssertEqual(
            String(decoding: try XCTUnwrap(request.httpBody), as: UTF8.self),
            #"{"contact_id":"city_clinic","purpose":"doctor_appointment"}"#)
    }

    func testStartCallKeepsBasePathPrefix() async throws {
        let http = FakeHTTP()
        let config = BackendConfig(baseURL: URL(string: "https://a.example.test/api")!, appToken: "x")
        let client = BackendClient(config: config, http: http, transport: FakeTransport())

        _ = try await client.startCall(contactID: "c1", purpose: .doctorAppointment)

        let url = await http.requests.first?.url?.absoluteString
        XCTAssertEqual(url, "https://a.example.test/api/calls")
    }

    func testStartCallThrowsOnNon2xx() async {
        let client = BackendClient(
            config: testConfig, http: FakeHTTP(status: 403, body: #"{"detail":"not allowed"}"#),
            transport: FakeTransport())
        do {
            _ = try await client.startCall(contactID: "stranger", purpose: .doctorAppointment)
            XCTFail("a 403 must not look like a started call")
        } catch {
            XCTAssertEqual(error as? BackendError, .httpStatus(403))
        }
    }

    // MARK: WebSocket

    func testConnectOpensCallSocketWithBearerToken() async throws {
        let transport = FakeTransport()
        let client = BackendClient(config: testConfig, http: FakeHTTP(), transport: transport)

        await client.connect(callID: "call_123")

        let requests = await transport.requests
        let request = try XCTUnwrap(requests.first)
        XCTAssertEqual(request.url?.absoluteString, "wss://backend.example.test/calls/call_123/ws")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer test-token")
    }

    func testEventsDecodeFramesAndDropMalformedOnes() async {
        let transport = FakeTransport()
        let client = BackendClient(config: testConfig, http: FakeHTTP(), transport: transport)
        await client.connect(callID: "call_123")
        let events = await client.events

        await transport.push(#"{"type":"status","state":"in_call"}"#)
        await transport.push("not json")
        await transport.push(#"{"type":"draft","text":"missing turn"}"#)
        await transport.push(#"{"type":"something_new"}"#)
        await transport.push(#"{"type":"spoken","turn_id":"t1"}"#)
        await transport.drop()

        var received: [ServerMessage] = []
        for await event in events { received.append(event) }
        XCTAssertEqual(
            received,
            [.status(.inCall), .unknown(type: "something_new"), .spoken(turnID: TurnID("t1")!)])
    }

    func testEventsFinishWhenSocketDrops() async {
        let transport = FakeTransport()
        let client = BackendClient(config: testConfig, http: FakeHTTP(), transport: transport)
        await client.connect(callID: "call_123")
        let events = await client.events

        await transport.drop()

        var count = 0
        for await _ in events { count += 1 }
        XCTAssertEqual(count, 0)
    }

    // MARK: Socket close

    func testOnlyBackendCloseCodesMapToTerminalReasons() {
        XCTAssertEqual(CallSocketClose(code: 4401), .unauthorized)
        XCTAssertEqual(CallSocketClose(code: 4404), .unknownCall)
        XCTAssertEqual(CallSocketClose(code: 4409), .replaced)
        for code in [nil, 1000, 1001, 1006, 1011, 4400, 4403, 4410] {
            XCTAssertEqual(CallSocketClose(code: code), .dropped, "code \(String(describing: code))")
        }
    }

    func testOnlyAPlainDropAllowsReconnecting() {
        XCTAssertTrue(CallSocketClose.dropped.allowsReconnect)
        XCTAssertFalse(CallSocketClose.unauthorized.allowsReconnect)
        XCTAssertFalse(CallSocketClose.unknownCall.allowsReconnect)
        XCTAssertFalse(CallSocketClose.replaced.allowsReconnect)
    }

    func testCloseCodeIsReportedOnceEventsFinish() async {
        let cases: [(Int?, CallSocketClose)] = [
            (nil, .dropped), (1000, .dropped), (4401, .unauthorized), (4404, .unknownCall),
            (4409, .replaced),
        ]
        for (code, expected) in cases {
            let transport = FakeTransport()
            let client = BackendClient(config: testConfig, http: FakeHTTP(), transport: transport)
            await client.connect(callID: "call_123")
            let events = await client.events
            let open = await client.lastClose
            XCTAssertNil(open, "an open socket has no close reason")

            await transport.drop(code: code)
            for await _ in events {}

            let close = await client.lastClose
            XCTAssertEqual(close, expected, "code \(String(describing: code))")
        }
    }

    func testReconnectClearsTheOldCloseReason() async {
        let transport = FakeTransport()
        let client = BackendClient(config: testConfig, http: FakeHTTP(), transport: transport)
        await client.connect(callID: "call_123")
        let events = await client.events
        await transport.drop(code: 4404)
        for await _ in events {}

        await client.connect(callID: "call_123")

        let close = await client.lastClose
        XCTAssertNil(close)
    }

    func testReplacedConnectionDoesNotReportItsClose() async {
        let transport = FakeTransport()
        let client = BackendClient(config: testConfig, http: FakeHTTP(), transport: transport)
        await client.connect(callID: "call_123")
        let old = await client.events

        await client.connect(callID: "call_123")
        for await _ in old {}

        let close = await client.lastClose
        XCTAssertNil(close, "closing the old socket on purpose is not a close of the new one")
    }

    func testEventsBeforeConnectAreAlreadyFinished() async {
        let client = BackendClient(config: testConfig, http: FakeHTTP(), transport: FakeTransport())
        var count = 0
        for await _ in await client.events { count += 1 }
        XCTAssertEqual(count, 0)
    }

    func testSendWritesWireJSON() async throws {
        let transport = FakeTransport()
        let client = BackendClient(config: testConfig, http: FakeHTTP(), transport: transport)
        await client.connect(callID: "call_123")

        try await client.send(.chips(turnID: TurnID("t1")!, chips: [.no, .morning]))
        try await client.send(.end)

        let sent = await transport.sent
        XCTAssertEqual(
            sent, [#"{"chips":["no","morning"],"turn_id":"t1","type":"chips"}"#, #"{"type":"end"}"#])
    }

    func testSendWithoutSocketThrows() async {
        let client = BackendClient(config: testConfig, http: FakeHTTP(), transport: FakeTransport())
        do {
            try await client.send(.stop)
            XCTFail("sending without a socket must fail loudly")
        } catch {
            XCTAssertEqual(error as? WebSocketTransportError, .notConnected)
        }
    }

    func testDisconnectClosesTransport() async {
        let transport = FakeTransport()
        let client = BackendClient(config: testConfig, http: FakeHTTP(), transport: transport)
        await client.connect(callID: "call_123")

        await client.disconnect()

        let closes = await transport.closeCount
        XCTAssertEqual(closes, 1)
    }
}
