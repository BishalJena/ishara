import CallSession
import Foundation

/// In-memory WebSocket: records upgrade requests and sent frames; tests push frames or drop it.
actor FakeTransport: WebSocketTransport {
    private(set) var requests: [URLRequest] = []
    private(set) var sent: [String] = []
    private(set) var closeCount = 0
    private(set) var closeCode: Int?
    private var continuation: AsyncStream<String>.Continuation?

    func connect(_ request: URLRequest) async -> AsyncStream<String> {
        continuation?.finish()
        closeCode = nil
        requests.append(request)
        let (frames, continuation) = AsyncStream<String>.makeStream()
        self.continuation = continuation
        return frames
    }

    func send(_ text: String) async throws {
        guard continuation != nil else { throw WebSocketTransportError.notConnected }
        sent.append(text)
    }

    func close() async {
        closeCount += 1
        drop()
    }

    func push(_ frame: String) {
        continuation?.yield(frame)
    }

    /// The socket goes away, with the server's close code if it sent one
    /// (nil: the network dropped).
    func drop(code: Int? = nil) {
        closeCode = code
        continuation?.finish()
        continuation = nil
    }
}

/// Answers `POST /calls` with one canned response and records each request.
actor FakeHTTP: HTTPClient {
    private(set) var requests: [URLRequest] = []
    private let status: Int
    private let body: String

    init(status: Int = 200, body: String = #"{"call_id":"call_1","state":"dialing"}"#) {
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

let testBackend = BackendConfig(baseURL: URL(string: "https://backend.example.test")!, appToken: "test-token")
