import CallSession
import SwiftUI

/// The notes after a delegated call (D9): outcome, what happened, what is still open, and the
/// full transcript. Summaries can be wrong; the transcript is what was actually said.
struct NotesView: View {
    let model: NotesModel
    let onDone: () -> Void

    var body: some View {
        NavigationStack {
            List {
                if let notes = model.notes {
                    Section {
                        Label {
                            Text(NotesModel.describe(outcome: notes.outcome, ready: notes.ready))
                        } icon: {
                            // VoiceOver read the check mark as a separate "Selected".
                            Image(systemName: notes.outcome == "booked" ? "checkmark.circle.fill" : "info.circle")
                                .accessibilityHidden(true)
                        }
                        .font(.headline)
                        .accessibilityElement(children: .combine)
                        .accessibilityIdentifier("notes.outcome")
                    } header: {
                        Text("Call with \(model.contactName)")
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
                            VStack(alignment: .leading, spacing: 2) {
                                Text(entry.speaker == .agent ? "Agent (for you)" : "They said")
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(entry.speaker == .agent ? Color.blue : Color.secondary)
                                Text(entry.text)
                            }
                            .accessibilityElement(children: .combine)
                        }
                    }
                    if let summary = notes.bolnaSummary {
                        Section {
                            Text(summary)
                        } header: {
                            Text("Automatic summary")
                        } footer: {
                            Text("Written by the call service's AI. It can be wrong; the transcript is what was said.")
                        }
                    }
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
            .task { await model.run() }
        }
    }
}
