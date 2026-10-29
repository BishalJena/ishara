import CallSession
import SwiftUI

/// A saved call, read only: its Call for me notes when they were loaded, otherwise the
/// captions the call screen showed. Read from the history, so notes that arrive while it is
/// open (Bolna's late summary) show up.
struct RecentCallView: View {
    let history: CallHistory
    let id: UUID

    var body: some View {
        if let record = history.records.first(where: { $0.id == id }) {
            content(record)
        }
    }

    private func content(_ record: CallRecord) -> some View {
        List {
            if let notes = record.notes {
                NotesSections(notes: notes, contactName: record.contactName)
            } else {
                Section {
                    OutcomeLabel(text: record.outcomeText, systemImage: "info.circle")
                } header: {
                    Text("Call with \(record.contactName)")
                }
                Section("Captions") {
                    if record.captions.isEmpty {
                        Text("No captions in this call.").foregroundStyle(.secondary)
                    }
                    ForEach(Array(record.captions.enumerated()), id: \.offset) { _, line in
                        TranscriptRow(speaker: speakerName(line.speaker), text: line.text, isAgent: line.speaker == .agent)
                    }
                }
            }
        }
        .navigationTitle(record.date.formatted(date: .abbreviated, time: .shortened))
        .navigationBarTitleDisplayMode(.inline)
    }

    /// The call screen's names for who spoke (`CaptionHistory`).
    private func speakerName(_ speaker: CallRecord.Line.Speaker) -> String {
        switch speaker {
        case .receptionist: "Receptionist"
        case .agent: "Ishara (voice)"
        case .user: "You"
        }
    }
}
