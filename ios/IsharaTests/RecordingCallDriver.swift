import Foundation
@testable import Ishara

/// Records every command the view model sends. Tests feed events straight into
/// `ActiveCallViewModel.handle(_:)`, so the stream never yields.
@MainActor
final class RecordingCallDriver: CallDriver {
    struct ChipUpdate: Equatable {
        let turnID: TurnID
        let words: [String]
    }

    struct Approval: Equatable {
        let turnID: TurnID
        let text: String
    }

    let events: AsyncStream<CallEvent>
    private let continuation: AsyncStream<CallEvent>.Continuation

    private(set) var started: [CallSetup] = []
    private(set) var chipUpdates: [ChipUpdate] = []
    private(set) var approvals: [Approval] = []
    private(set) var stopCount = 0
    private(set) var endCount = 0

    init() {
        (events, continuation) = AsyncStream.makeStream(of: CallEvent.self)
    }

    var commandCount: Int {
        started.count + chipUpdates.count + approvals.count + stopCount + endCount
    }

    func start(_ setup: CallSetup) { started.append(setup) }
    func updateChips(turnID: TurnID, words: [String]) { chipUpdates.append(ChipUpdate(turnID: turnID, words: words)) }
    func approve(turnID: TurnID, text: String) { approvals.append(Approval(turnID: turnID, text: text)) }
    func stop() { stopCount += 1 }
    func end() { endCount += 1 }
}
