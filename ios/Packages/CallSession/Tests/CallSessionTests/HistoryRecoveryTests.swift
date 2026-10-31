import Foundation
import XCTest
@testable import CallSession

@MainActor
final class HistoryRecoveryTests: XCTestCase {
    func testHistoryRestoresBothSpeakersWithoutReplayingApprovals() throws {
        let sink = FakeSink()
        let store = TurnStore(sink: sink)
        let frame = #"{"type":"history","entries":[{"speaker":"receptionist","text":"A question","at":1},{"speaker":"agent","text":"An answer","at":2}]}"#
        let message = try JSONDecoder().decode(ServerMessage.self, from: Data(frame.utf8))
        store.receive(message)
        store.receive(message)
        XCTAssertEqual(store.captions.map(\.text), ["A question", "An answer"])
        XCTAssertEqual(store.captions.map(\.speaker), [.receptionist, .agent])
        XCTAssertNil(store.proposal)
        XCTAssertTrue(sink.sent.isEmpty)
        store.receive(.status(.ended))
        store.receive(message)
        XCTAssertEqual(store.captions.count, 2)
        XCTAssertEqual(store.state, .ended)
    }
}
