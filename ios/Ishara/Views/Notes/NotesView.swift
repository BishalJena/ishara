import CallSession
import SwiftUI

/// The notes after a delegated call (D9): outcome, what happened, what is still open, and the
/// full transcript. Summaries can be wrong; the transcript is what was actually said. The
/// model loads them on its own (`NotesModel.start()`); this screen only shows them.
struct NotesView: View {
    let model: NotesModel
    let onDone: () -> Void

    var body: some View {
        NavigationStack {
            List {
                if let notes = model.notes {
                    NotesSections(notes: notes, contactName: model.contactName)
                } else if model.failure == nil {
                    ProgressView("Loading the notes…")
                }
                if let failure = model.failure {
                    Label(failure, systemImage: "exclamationmark.triangle.fill").foregroundStyle(.red)
                }
            }
            .navigationTitle("Call notes")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done", action: onDone)
                        .accessibilityIdentifier("notes.done")
                }
                ToolbarItem(placement: .topBarLeading) {
                    Button {
                        Task { await model.refresh() }
                    } label: {
                        Label("Refresh", systemImage: "arrow.clockwise")
                    }
                    .disabled(model.isLoading)
                    .accessibilityIdentifier("notes.refresh")
                }
            }
        }
    }
}

/// The notes themselves, shared by the notes screen after a call and a saved call in
/// Recent calls.
struct NotesSections: View {
    let notes: CallNotes
    let contactName: String

    var body: some View {
        Section {
            OutcomeLabel(text: NotesModel.describe(outcome: notes.outcome, ready: notes.ready),
                         systemImage: notes.outcome == "booked" ? "checkmark.circle.fill" : "info.circle")
        } header: {
            Text("Call with \(contactName)")
        }
        if !notes.summary.isEmpty {
            Section("What happened") {
                ForEach(notes.summary, id: \.self) { Text($0) }
            }
        }
        if !notes.openQuestions.isEmpty {
            Section("Still open") {
                ForEach(notes.openQuestions, id: \.self) {
                    Label($0, systemImage: "questionmark.circle").foregroundStyle(.orange)
                }
            }
        }
        if let brief = notes.brief {
            Section("The brief you approved") { Text(brief) }
        }
        Section("Transcript") {
            if notes.transcript.isEmpty {
                Text("Nothing was heard on the call.").foregroundStyle(.secondary)
            }
            ForEach(Array(notes.transcript.enumerated()), id: \.offset) { _, entry in
                TranscriptRow(speaker: entry.speaker == .agent ? "Agent (for you)" : "They said",
                              text: entry.text, isAgent: entry.speaker == .agent)
            }
        }
        if let summary = notes.bolnaSummary {
            Section {
                Text(summary)
                    .accessibilityIdentifier("notes.bolnaSummary")
            } header: {
                Text("Automatic summary")
            } footer: {
                Text("Written by the call service's AI. It can be wrong; the transcript is what was said.")
            }
        }
    }
}

/// The call's outcome, read as one element.
struct OutcomeLabel: View {
    let text: String
    let systemImage: String

    var body: some View {
        Label {
            Text(text)
        } icon: {
            // VoiceOver read the check mark as a separate "Selected".
            Image(systemName: systemImage)
                .accessibilityHidden(true)
        }
        .font(.headline)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("notes.outcome")
    }
}

/// One line of a call's transcript: who spoke, then what they said.
struct TranscriptRow: View {
    let speaker: String
    let text: String
    let isAgent: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(speaker)
                .font(.caption.weight(.semibold))
                .foregroundStyle(isAgent ? Color.blue : Color.secondary)
            Text(text)
        }
        .accessibilityElement(children: .combine)
    }
}
