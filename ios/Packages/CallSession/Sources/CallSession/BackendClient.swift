import Foundation

/// Where the backend lives and the demo app token. Both come from the app's configuration;
/// nothing here is hardcoded.
public struct BackendConfig: Sendable, Equatable {
    /// REST base, e.g. `https://<app>.herokuapp.com`.
    public var baseURL: URL
    /// WebSocket base. Defaults to `baseURL` with `https`→`wss` / `http`→`ws`.
    public var webSocketBaseURL: URL
    /// `APP_TOKEN`, sent as `Authorization: Bearer <token>`.
    public var appToken: String

    public init(baseURL: URL, appToken: String, webSocketBaseURL: URL? = nil) {
        self.baseURL = baseURL
        self.appToken = appToken
        self.webSocketBaseURL = webSocketBaseURL ?? Self.webSocketURL(for: baseURL)
    }

    private static func webSocketURL(for url: URL) -> URL {
        guard var components = URLComponents(url: url, resolvingAgainstBaseURL: false) else {
            return url
        }
        switch components.scheme?.lowercased() {
        case "https": components.scheme = "wss"
        case "http": components.scheme = "ws"
        default: break
        }
        return components.url ?? url
    }
}

/// The HTTP call `BackendClient` needs; `URLSession` conforms.
public protocol HTTPClient: Sendable {
    func perform(_ request: URLRequest) async throws -> (Data, URLResponse)
}

extension URLSession: HTTPClient {
    public func perform(_ request: URLRequest) async throws -> (Data, URLResponse) {
        try await data(for: request)
    }
}

public enum BackendError: Error, Equatable {
    /// `POST /calls` answered with a non-2xx status (401 bad token, 403 not allowlisted, ...).
    case httpStatus(Int)
    case notHTTPResponse
}

/// Why the call socket closed, from the backend's close codes (backend/app/calls.py).
public enum CallSocketClose: Equatable, Sendable {
    /// Network loss, a normal close or a code the backend doesn't use. Reconnecting may help.
    case dropped
    /// 4401: the backend rejected `APP_TOKEN`.
    case unauthorized
    /// 4404: the backend doesn't know this call, e.g. it restarted and lost it.
    case unknownCall
    /// 4409: another socket for this call took over.
    case replaced

    public init(code: Int?) {
        switch code {
        case 4401: self = .unauthorized
        case 4404: self = .unknownCall
        case 4409: self = .replaced
        default: self = .dropped
        }
    }

    /// Only a plain drop may be reconnected. The same token or call id would be refused
    /// again, and taking a replaced socket back would make two sockets evict each other.
    public var allowsReconnect: Bool { self == .dropped }
}

/// Something that can put an `AppMessage` on the call socket.
public protocol AppMessageSending: Sendable {
    func send(_ message: AppMessage) async throws
}

/// Talks to the Ishara backend: `POST /calls`, then one WebSocket per call.
public actor BackendClient: AppMessageSending {
    private let config: BackendConfig
    private let http: any HTTPClient
    private let transport: any WebSocketTransport
    private var pump: Task<Void, Never>?

    /// Server messages from the current connection. Finishes when the socket closes; frames
    /// that aren't valid JSON for a known message are dropped (unknown types arrive as
    /// `.unknown`). Empty and finished before `connect`.
    public private(set) var events: AsyncStream<ServerMessage>

    /// Why the current connection's socket closed. Set just before `events` finishes; nil
    /// while it is open or before `connect`.
    public private(set) var lastClose: CallSocketClose?

    public init(
        config: BackendConfig,
        http: any HTTPClient = URLSession.shared,
        transport: any WebSocketTransport = URLSessionWebSocketTransport()
    ) {
        self.config = config
        self.http = http
        self.transport = transport
        let (idle, continuation) = AsyncStream<ServerMessage>.makeStream()
        continuation.finish()
        events = idle
    }

    /// Asks the backend to place a call. The backend only dials allowlisted contacts.
    public func startCall(contactID: String, purpose: CallPurpose) async throws -> CallStart {
        try await startCall(StartCallRequest(contactID: contactID, purpose: purpose))
    }

    /// Places a live or delegated call (D9). Starting a delegated call with a brief id is
    /// the user's one approval of that brief.
    public func startCall(_ body: StartCallRequest) async throws -> CallStart {
        try await post(body, path: "calls", as: CallStart.self)
    }

    /// `POST /briefs` (D9): the brief the user reads and approves before a delegated call.
    public func createBrief(_ body: BriefRequest) async throws -> Brief {
        try await post(body, path: "briefs", as: Brief.self)
    }

    /// `GET /calls/{id}/notes` (D9): transcript, outcome and summary; `ready` once the call ended.
    public func notes(callID: String) async throws -> CallNotes {
        let url = config.baseURL.appending(path: "calls").appending(path: callID).appending(path: "notes")
        let (data, response) = try await http.perform(authorizedRequest(url: url))
        return try decoded(CallNotes.self, data: data, response: response)
    }

    private func post<Body: Encodable, Reply: Decodable>(
        _ body: Body, path: String, as reply: Reply.Type
    ) async throws -> Reply {
        var request = authorizedRequest(url: config.baseURL.appending(path: path))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try WireCoding.makeEncoder().encode(body)
        let (data, response) = try await http.perform(request)
        return try decoded(reply, data: data, response: response)
    }

    private func decoded<Reply: Decodable>(_: Reply.Type, data: Data, response: URLResponse) throws -> Reply {
        guard let http = response as? HTTPURLResponse else { throw BackendError.notHTTPResponse }
        guard (200..<300).contains(http.statusCode) else {
            throw BackendError.httpStatus(http.statusCode)
        }
        return try JSONDecoder().decode(Reply.self, from: data)
    }

    /// Opens `{ws_base}/calls/{call_id}/ws` and replaces `events` with its messages.
    public func connect(callID: String) async {
        pump?.cancel()
        let url = config.webSocketBaseURL.appending(path: "calls").appending(path: callID)
            .appending(path: "ws")
        let frames = await transport.connect(authorizedRequest(url: url))
        let (messages, continuation) = AsyncStream<ServerMessage>.makeStream()
        events = messages
        lastClose = nil
        pump = Task { [transport] in
            for await frame in frames {
                guard let message = try? WireCoding.decodeServerMessage(frame) else { continue }
                continuation.yield(message)
            }
            // A replaced connection's pump is cancelled and must not report its close.
            if !Task.isCancelled {
                let code = await transport.closeCode
                if !Task.isCancelled { lastClose = CallSocketClose(code: code) }
            }
            continuation.finish()
        }
    }

    public func send(_ message: AppMessage) async throws {
        try await transport.send(WireCoding.encodeText(message))
    }

    public func disconnect() async {
        await transport.close()
    }

    private func authorizedRequest(url: URL) -> URLRequest {
        var request = URLRequest(url: url)
        request.setValue("Bearer \(config.appToken)", forHTTPHeaderField: "Authorization")
        return request
    }
}
