import Foundation

@testable import CallSession

/// In-memory WebSocket: records requests and sent frames; tests push frames or drop it.
actor FakeTransport: WebSocketTransport {
    private(set) var requests: [URLRequest] = []
    private(set) var sent: [String] = []
    private(set) var closeCount = 0
    private var continuation: AsyncStream<String>.Continuation?
    private var failSends = false

    func connect(_ request: URLRequest) async -> AsyncStream<String> {
        continuation?.finish()
        requests.append(request)
        let (frames, continuation) = AsyncStream<String>.makeStream()
        self.continuation = continuation
        return frames
    }

    func send(_ text: String) async throws {
        guard continuation != nil, !failSends else { throw WebSocketTransportError.notConnected }
        sent.append(text)
    }

    func close() async {
        closeCount += 1
        drop()
    }

    func push(_ frame: String) {
        continuation?.yield(frame)
    }

    /// Simulates the socket going away.
    func drop() {
        continuation?.finish()
        continuation = nil
    }

    func setFailSends(_ fail: Bool) {
        failSends = fail
    }
}

/// Returns one canned response and records each request.
actor FakeHTTP: HTTPClient {
    private(set) var requests: [URLRequest] = []
    private let status: Int
    private let body: String

    init(status: Int = 200, body: String = #"{"call_id":"call_123","state":"dialing"}"#) {
        self.status = status
        self.body = body
    }

    func perform(_ request: URLRequest) async throws -> (Data, URLResponse) {
        requests.append(request)
        let response = HTTPURLResponse(
            url: request.url!, statusCode: status, httpVersion: "HTTP/1.1", headerFields: nil)!
        return (Data(body.utf8), response)
    }
}

/// Records sends in order; can be told to fail.
actor RecordingSender: AppMessageSending {
    private(set) var sent: [AppMessage] = []
    private var failing = false

    func send(_ message: AppMessage) async throws {
        if failing { throw WebSocketTransportError.notConnected }
        sent.append(message)
    }

    func setFailing(_ value: Bool) {
        failing = value
    }
}

let testConfig = BackendConfig(
    baseURL: URL(string: "https://backend.example.test")!, appToken: "test-token")

/// Polls `condition` until it holds or `timeout` passes. For effects that cross actors.
func eventually(
    timeout: Duration = .seconds(2), _ condition: @Sendable () async -> Bool
) async -> Bool {
    let clock = ContinuousClock()
    let deadline = clock.now.advanced(by: timeout)
    while clock.now < deadline {
        if await condition() { return true }
        try? await Task.sleep(for: .milliseconds(5))
    }
    return await condition()
}
