import CallSession
import Foundation
import Observation

/// Decision D9, last step: the call's notes (`GET /calls/{id}/notes`). The backend marks them
/// `ready` once the call has ended; Bolna's own summary can arrive a little later through its
/// webhook, so the app keeps checking for a short while, whether the notes screen is open or not.
@MainActor
@Observable
final class NotesModel {
    static let refreshInterval: Duration = .seconds(3)
    static let maxRefreshes = 10

    let contactName: String
    private(set) var notes: CallNotes?
    private(set) var failure: String?
    private(set) var isLoading = false
    private(set) var isPolling = false

    @ObservationIgnored private let driver: any CallDriver
    @ObservationIgnored private let onNotes: (CallNotes) -> Void
    @ObservationIgnored private let sleep: @Sendable (Duration) async throws -> Void
    @ObservationIgnored private var polling: Task<Void, Never>?

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

    /// The call ended and its canonical presentation is ready.
    var isComplete: Bool { notes.map { $0.ready && ($0.presentation?.status == "ready" || $0.outcome == "no_answer") } ?? false }
    var awaitingSummary: Bool { (isPolling || isLoading) && notes?.presentation?.status != "ready" && notes?.outcome != "no_answer" }

    /// Starts `run()` once, owned by this model rather than a screen, so it goes on after the
    /// notes screen closes. Later calls hand back the same task.
    @discardableResult
    func start() -> Task<Void, Never> {
        if let polling { return polling }
        let task = Task { await run() }
        polling = task
        return task
    }

    func stop() {
        polling?.cancel()
    }

    /// Loads the notes, then refreshes until they are complete or the attempts run out.
    func run() async {
        isPolling = true
        defer { isPolling = false }
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
        case "callback": "Follow-up needed"
        case "declined": "Nothing suitable was offered"
        case "no_answer": "Nobody answered"
        case "done": "Finished"
        default: "Outcome not confirmed"
        }
    }
}

// Blank provider fields are not a completed automatic summary.
extension CallNotes {
    var automaticSummary: String? {
        guard let text = bolnaSummary?.trimmingCharacters(in: .whitespacesAndNewlines), !text.isEmpty else { return nil }
        return text
    }
}

/// Legacy records stay useful while the backend prepares their canonical presentation.
extension CallNotes {
    var summaryTitle: String {
        if let title = presentation?.title.trimmingCharacters(in: .whitespacesAndNewlines), !title.isEmpty { return title }
        return Self.requestTitle(brief)
    }

    static func requestTitle(_ request: String?) -> String {
        guard var text = request?.trimmingCharacters(in: .whitespacesAndNewlines), !text.isEmpty else { return "Call summary" }
        if text.hasPrefix("Call on behalf of ") {
            if let request = text.range(of: "Request:") {
                text = String(text[request.upperBound...]).trimmingCharacters(in: .whitespacesAndNewlines)
            } else if let goal = text.range(of: ", to ") {
                text = String(text[goal.upperBound...])
            }
        }
        for marker in [" Preferred:", " Reason, if asked:", " May share:", " Will not agree"] {
            if let boundary = text.range(of: marker) { text = String(text[..<boundary.lowerBound]) }
        }
        for prefix in ["I would like to ", "I'd like to ", "I want to ", "Please ", "Can you "] {
            if text.lowercased().hasPrefix(prefix.lowercased()) { text = String(text.dropFirst(prefix.count)); break }
        }
        let words = text.split(whereSeparator: { $0.isWhitespace || $0 == "\n" }).prefix(7)
        let title = words.joined(separator: " ").trimmingCharacters(in: CharacterSet(charactersIn: ".!?"))
        guard !title.isEmpty else { return "Call summary" }
        return title.prefix(1).uppercased() + title.dropFirst()
    }

    var summaryOverview: String {
        if let text = presentation?.overview, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return text }
        switch outcome {
        case "booked": return "The appointment was booked."
        case "done": return "The request was handled."
        case "no_answer": return "Nobody answered the call."
        case "callback": return "A follow-up is needed to finish the request."
        case "declined": return "No suitable offer was accepted."
        default: return "The call ended without a confirmed outcome."
        }
    }
}
