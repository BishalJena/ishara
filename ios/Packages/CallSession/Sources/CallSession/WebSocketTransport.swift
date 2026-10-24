import Foundation

/// A text WebSocket. `connect` returns the incoming frames; the stream finishes when the
/// socket closes for any reason, which callers treat as "disconnected".
public protocol WebSocketTransport: Sendable {
    func connect(_ request: URLRequest) async -> AsyncStream<String>
    func send(_ text: String) async throws
    func close() async
    /// The close code the server sent for the latest socket, once its stream has finished.
    /// Nil while the socket is open, or when it died without a close frame.
    var closeCode: Int? { get async }
}

public enum WebSocketTransportError: Error, Equatable {
    case notConnected
}

/// Sends a ping every `interval` until cancelled or a ping fails.
///
/// Heroku's router closes a WebSocket that sees no traffic for 55 s, and the receptionist
/// can talk for a long time while the app sends nothing, so the client keeps the socket warm.
struct PingLoop: Sendable {
    let interval: Duration
    let sleep: @Sendable (Duration) async throws -> Void

    init(
        interval: Duration,
        sleep: @escaping @Sendable (Duration) async throws -> Void = { try await Task.sleep(for: $0) }
    ) {
        self.interval = interval
        self.sleep = sleep
    }

    /// Returns when the task is cancelled, or when `ping` throws (the socket is dead).
    func run(ping: @Sendable () async throws -> Void) async {
        do {
            while true {
                try await sleep(interval)
                try Task.checkCancellation()
                try await ping()
            }
        } catch {
            return
        }
    }
}

/// `WebSocketTransport` over `URLSessionWebSocketTask`.
public actor URLSessionWebSocketTransport: WebSocketTransport {
    /// Well under Heroku's 55 s idle cut-off.
    public static let defaultPingInterval: Duration = .seconds(20)

    private let session: URLSession
    let pingLoop: PingLoop
    private var task: URLSessionWebSocketTask?
    private var workers: [Task<Void, Never>] = []
    public private(set) var closeCode: Int?

    public init(session: URLSession = .shared, pingInterval: Duration = defaultPingInterval) {
        self.init(session: session, pingLoop: PingLoop(interval: pingInterval))
    }

    init(session: URLSession, pingLoop: PingLoop) {
        self.session = session
        self.pingLoop = pingLoop
    }

    /// Opens a socket for `request` (headers such as Authorization are sent with the
    /// upgrade request), closing any previous one.
    public func connect(_ request: URLRequest) async -> AsyncStream<String> {
        close()
        let task = session.webSocketTask(with: request)
        self.task = task
        closeCode = nil
        let (frames, continuation) = AsyncStream<String>.makeStream()

        let receiver = Task {
            defer { continuation.finish() }
            while !Task.isCancelled {
                guard let message = try? await task.receive() else {
                    recordClose(of: task)
                    return
                }
                switch message {
                case let .string(text):
                    continuation.yield(text)
                case let .data(data):
                    continuation.yield(String(decoding: data, as: UTF8.self))
                @unknown default:
                    continue
                }
            }
        }
        let pinger = Task { [pingLoop] in
            await pingLoop.run { try await task.sendPingAsync() }
            // A failed ping means the socket is gone; cancelling it ends `receive`.
            task.cancel(with: .goingAway, reason: nil)
        }
        workers = [receiver, pinger]
        continuation.onTermination = { _ in
            receiver.cancel()
            pinger.cancel()
            task.cancel(with: .normalClosure, reason: nil)
        }
        task.resume()
        return frames
    }

    public func send(_ text: String) async throws {
        guard let task else { throw WebSocketTransportError.notConnected }
        try await task.send(.string(text))
    }

    public func close() {
        workers.forEach { $0.cancel() }
        workers = []
        task?.cancel(with: .normalClosure, reason: nil)
        task = nil
    }

    private func recordClose(of task: URLSessionWebSocketTask) {
        // A socket replaced by `connect` must not overwrite the new socket's code.
        guard task === self.task else { return }
        // `.invalid` (0) means no close frame arrived. The backend's 44xx codes have no
        // named case, but `rawValue` still carries them.
        let code = task.closeCode.rawValue
        closeCode = code == URLSessionWebSocketTask.CloseCode.invalid.rawValue ? nil : code
    }
}

extension URLSessionWebSocketTask {
    fileprivate func sendPingAsync() async throws {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            sendPing { error in
                if let error {
                    continuation.resume(throwing: error)
                } else {
                    continuation.resume()
                }
            }
        }
    }
}
