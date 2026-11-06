import CallSession
import SwiftUI

/// Home: the calls kept on this phone, newest first. Tap one to read it again; swipe it
/// away to delete it. Hidden until there is a call (or a problem) to show.
struct RecentCallsSection: View {
    let history: CallHistory
    var onRefresh: ((CallRecord) async -> Void)? = nil

    var body: some View {
        if !history.records.isEmpty || history.problem != nil {
            Section {
                if let problem = history.problem {
                    Label(problem, systemImage: "exclamationmark.triangle.fill")
                        .foregroundStyle(.orange)
                        .accessibilityIdentifier("recentCalls.problem")
                }
                ForEach(history.records) { record in
                    NavigationLink {
                        RecentCallView(history: history, id: record.id, onRefresh: onRefresh)
                    } label: {
                        RecentCallRow(record: record)
                    }
                    .accessibilityIdentifier("recentCalls.row")
                }
                .onDelete { offsets in
                    offsets.map { history.records[$0].id }.forEach(history.delete)
                }
            } header: {
                Text("Recent calls")
            } footer: {
                Text("Saved on this phone. Completed notes also have a 24-hour backend recovery copy. Swipe left to remove the local copy.")
            }
        }
    }
}

private struct RecentCallRow: View {
    let record: CallRecord

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: record.mode == .delegated ? "person.wave.2.fill" : "phone.fill")
                .foregroundStyle(.secondary)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(record.displayTitle)
                    .font(.headline)
                Text(record.contactName).font(.caption).foregroundStyle(.secondary)
                Text(record.outcomeText)
                    .font(.subheadline)
                Text(record.date, format: .dateTime.day().month().hour().minute())
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .accessibilityElement(children: .combine)
    }
}

extension CallRecord {
    /// The outcome in the notes' words, or what kind of call it was when there are no notes.
    var outcomeText: String {
        if let notes { return NotesModel.describe(outcome: notes.outcome, ready: notes.ready) }
        return switch mode {
        case .live: "You signed the call"
        case .delegated: "Call for me: the notes weren't loaded"
        case .steer: "Ishara ran the call: the notes weren't loaded"
        }
    }
}
