import XCTest

@testable import CallSession

@MainActor
final class MessageOutboxTests: XCTestCase {
    private let t1 = TurnID("t1")!

    func testSendsInQueueOrder() async {
        let sender = RecordingSender()
        let outbox = MessageOutbox(sender: sender)
        let expected: [AppMessage] = [
            .chips(turnID: t1, chips: [.hello]),
            .chips(turnID: t1, chips: [.hello, .doctor]),
            .approve(turnID: t1, text: "Hello."),
            .stop,
            .end,
        ]

        expected.forEach(outbox.send)

        let delivered = await eventually { await sender.sent.count == expected.count }
        XCTAssertTrue(delivered)
        let sent = await sender.sent
        XCTAssertEqual(sent, expected)
    }

    func testDiscardPendingDropsQueuedMessages() async {
        let sender = RecordingSender()
        let outbox = MessageOutbox(sender: sender)

        outbox.send(.approve(turnID: t1, text: "Hello."))
        outbox.discardPending()
        outbox.send(.end)

        let delivered = await eventually { await !sender.sent.isEmpty }
        XCTAssertTrue(delivered)
        try? await Task.sleep(for: .milliseconds(50))
        let sent = await sender.sent
        XCTAssertEqual(sent, [.end])
    }

    func testFailureDropsTheRestAndReportsOnce() async {
        let sender = RecordingSender()
        await sender.setFailing(true)
        let outbox = MessageOutbox(sender: sender)
        var failures = 0
        outbox.onFailure = { _ in failures += 1 }

        outbox.send(.approve(turnID: t1, text: "Hello."))
        outbox.send(.chips(turnID: t1, chips: [.yes]))

        let reported = await eventually { @MainActor in failures > 0 }
        XCTAssertTrue(reported)
        await sender.setFailing(false)
        outbox.send(.end)

        let delivered = await eventually { await !sender.sent.isEmpty }
        XCTAssertTrue(delivered)
        try? await Task.sleep(for: .milliseconds(50))
        let sent = await sender.sent
        XCTAssertEqual(sent, [.end], "messages queued before a failure must never go out later")
        XCTAssertEqual(failures, 1)
    }
}
