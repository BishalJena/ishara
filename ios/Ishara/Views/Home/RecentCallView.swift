import CallSession
import SwiftUI

/// A saved call, read only: its Call for me notes when they were loaded, otherwise the
/// captions the call screen showed.
struct RecentCallView: View {
    let record: CallRecord

    var body: some View {
        List {
            if let notes = record.notes {
                NotesSections(notes: notes, contactName: record.contactName)
            } else {
                Section {
                    Label(record.outcomeText, systemImage: "info.circle")
                        .font(.headline)
                        .accessibilityIdentifier("notes.outcome")
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
