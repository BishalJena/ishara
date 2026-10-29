import CallSession
import SwiftUI

/// Home: the calls kept on this phone, newest first. Tap one to read it again; swipe it
/// away to delete it. Hidden until there is a call (or a problem) to show.
struct RecentCallsSection: View {
    let history: CallHistory

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
                        RecentCallView(history: history, id: record.id)
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
                Text("Kept on this phone only. Swipe left on a call to delete it.")
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
                Text(record.contactName)
                    .font(.headline)
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
        }
    }
}
