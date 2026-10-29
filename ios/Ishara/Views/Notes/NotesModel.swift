import CallSession
import Foundation
import Observation

/// Decision D9, last step: the call's notes (`GET /calls/{id}/notes`). The backend marks them
/// `ready` once the call has ended; Bolna's own summary can arrive a little later through its
/// webhook, so the screen keeps checking for a short while.
@MainActor
@Observable
final class NotesModel {
    static let refreshInterval: Duration = .seconds(3)
    static let maxRefreshes = 10

    let contactName: String
    private(set) var notes: CallNotes?
    private(set) var failure: String?
    private(set) var isLoading = false

    @ObservationIgnored private let driver: any CallDriver
    @ObservationIgnored private let onNotes: (CallNotes) -> Void
    @ObservationIgnored private let sleep: @Sendable (Duration) async throws -> Void

    /// `onNotes` gets every set of notes loaded, so the saved call picks up Bolna's summary.
    init(
        contactName: String,
        driver: any CallDriver,
        onNotes: @escaping (CallNotes) -> Void = { _ in },
        sleep: @escaping @Sendable (Duration) async throws -> Void = { try await Task.sleep(for: $0) }
    ) {
        self.contactName = contactName
        self.driver = driver
        self.onNotes = onNotes
        self.sleep = sleep
    }

    /// Nothing more is expected: the call ended and Bolna's summary (if any) is in.
    var isComplete: Bool { notes.map { $0.ready && $0.bolnaSummary != nil } ?? false }

    /// Loads the notes, then refreshes until they are complete or the attempts run out.
    func run() async {
        for attempt in 0...Self.maxRefreshes {
            await refresh()
            guard !isComplete, attempt < Self.maxRefreshes else { return }
            do { try await sleep(Self.refreshInterval) } catch { return }
        }
    }

    func refresh() async {
        isLoading = true
        defer { isLoading = false }
        do {
            let loaded = try await driver.notes()
            notes = loaded
            failure = nil
            onNotes(loaded)
        } catch {
            failure = switch error as? BackendError {
            case .httpStatus(404)?: "The backend no longer has this call (it may have restarted)."
            case .httpStatus(let code)?: "The notes couldn't be loaded (HTTP \(code))."
            case .notHTTPResponse?: "The backend couldn't be reached."
            case nil: "The notes couldn't be loaded: \(error.localizedDescription)"
            }
        }
    }

    /// Plain words for the backend's outcome.
    nonisolated static func describe(outcome: String?, ready: Bool) -> String {
        guard ready else { return "The call is still being wrapped up" }
        return switch outcome {
        case "booked": "Booked"
        case "callback": "The agent will need to call back"
        case "declined": "Nothing suitable was offered"
        case "no_answer": "Nobody answered"
        case "done": "Finished"
        default: "Not confirmed: read the transcript"
        }
    }
}
