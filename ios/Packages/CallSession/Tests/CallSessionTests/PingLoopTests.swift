import XCTest

@testable import CallSession

final class PingLoopTests: XCTestCase {
    func testWaitsOneIntervalBeforeEveryPing() async {
        let log = EventLog()
        let loop = PingLoop(interval: .seconds(7)) { duration in
            log.append("sleep \(duration)")
            if log.count(of: "ping") == 3 { throw CancellationError() }
        }

        await loop.run { log.append("ping") }

        XCTAssertEqual(
            log.events,
            ["sleep 7.0 seconds", "ping", "sleep 7.0 seconds", "ping", "sleep 7.0 seconds", "ping",
             "sleep 7.0 seconds"])
    }

    func testDoesNotPingBeforeTheFirstIntervalElapses() async {
        let log = EventLog()
        let loop = PingLoop(interval: .seconds(20)) { _ in throw CancellationError() }

        await loop.run { log.append("ping") }

        XCTAssertEqual(log.events, [])
    }

    func testStopsAfterAPingFails() async {
        let log = EventLog()
        let loop = PingLoop(interval: .seconds(1)) { _ in log.append("sleep") }

        await loop.run {
            log.append("ping")
            if log.count(of: "ping") == 2 { throw URLError(.networkConnectionLost) }
        }

        XCTAssertEqual(log.events, ["sleep", "ping", "sleep", "ping"])
    }

    func testStopsWhenCancelled() async {
        let log = EventLog()
        let loop = PingLoop(interval: .seconds(3600))
        let running = Task { await loop.run { log.append("ping") } }

        running.cancel()
        await running.value

        XCTAssertEqual(log.events, [])
    }

    func testTransportPingsEveryTwentySecondsByDefault() async {
        XCTAssertEqual(URLSessionWebSocketTransport.defaultPingInterval, .seconds(20))
        let transport = URLSessionWebSocketTransport()
        let interval = await transport.pingLoop.interval
        XCTAssertEqual(interval, .seconds(20))
    }

    func testTransportUsesInjectedPingInterval() async {
        let transport = URLSessionWebSocketTransport(pingInterval: .seconds(5))
        let interval = await transport.pingLoop.interval
        XCTAssertEqual(interval, .seconds(5))
    }

    func testTransportSendBeforeConnectThrows() async {
        let transport = URLSessionWebSocketTransport()
        do {
            try await transport.send("{}")
            XCTFail("send before connect must throw")
        } catch {
            XCTAssertEqual(error as? WebSocketTransportError, .notConnected)
        }
    }
}

/// Thread-safe ordered log for closures that run off the test's thread.
final class EventLog: @unchecked Sendable {
    private let lock = NSLock()
    private var storage: [String] = []

    var events: [String] {
        lock.lock()
        defer { lock.unlock() }
        return storage
    }

    func append(_ event: String) {
        lock.lock()
        storage.append(event)
        lock.unlock()
    }

    func count(of event: String) -> Int {
        events.filter { $0 == event }.count
    }
}
