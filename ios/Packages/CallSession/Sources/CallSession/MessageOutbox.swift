import Foundation

/// Where `TurnStore` puts outgoing messages. Synchronous so a button tap updates state and
/// queues its message in one step, with no reordering between taps.
@MainActor
public protocol OutgoingMessageSink: AnyObject {
    func send(_ message: AppMessage)
    /// Drops everything queued but not yet handed to the socket.
    func discardPending()
}

/// Sends queued messages one at a time, in the order they were queued.
///
/// When a send fails, the rest of the queue is dropped and `onFailure` runs: nothing queued
/// before a failure is ever sent later on a new socket.
@MainActor
public final class MessageOutbox: OutgoingMessageSink {
    private let sender: any AppMessageSending
    private var queue: [AppMessage] = []
    private var draining: Task<Void, Never>?

    public var onFailure: ((any Error) -> Void)?

    public init(sender: any AppMessageSending) {
        self.sender = sender
    }

    public func send(_ message: AppMessage) {
        queue.append(message)
        guard draining == nil else { return }
        draining = Task { await drain() }
    }

    public func discardPending() {
        queue.removeAll()
    }

    private func drain() async {
        while !queue.isEmpty {
            let message = queue.removeFirst()
            do {
                try await sender.send(message)
            } catch {
                queue.removeAll()
                onFailure?(error)
            }
        }
        draining = nil
    }
}
