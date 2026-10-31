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
                    NotesSections(notes: notes, contactName: model.contactName, awaitingSummary: model.awaitingSummary)
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
    var awaitingSummary = false

    private var attentionLines: [String] {
        var seen = Set<String>()
        return (notes.openQuestions + notes.followUps).filter { seen.insert($0).inserted }
    }

    var body: some View {
        Section {
            CallSummaryContent(notes: notes, awaitingSummary: awaitingSummary)
        } header: {
            Text("Call summary").accessibilityIdentifier("notes.summaryTitle")
        }
        Section {
            OutcomeLabel(text: NotesModel.describe(outcome: notes.outcome, ready: notes.ready),
                         systemImage: notes.outcome == "booked" ? "checkmark.circle.fill" : "info.circle")
        } header: {
            Text("Call with \(contactName)")
        }
        if !notes.openQuestions.isEmpty || !notes.followUps.isEmpty {
            Section("What needs your attention") {
                ForEach(attentionLines, id: \.self) {
                    Label($0, systemImage: "questionmark.circle").foregroundStyle(.orange)
                }
            }
        }
        Section("Transcript") {
            if notes.transcript.isEmpty {
                Text("No transcript was captured for this call.").foregroundStyle(.secondary)
            }
            ForEach(Array(notes.transcript.enumerated()), id: \.offset) { _, entry in
                TranscriptRow(speaker: entry.speaker == .agent ? "Agent (for you)" : "They said",
                              text: entry.text, isAgent: entry.speaker == .agent)
            }
        }
        if notes.automaticSummary != nil && !notes.summary.isEmpty || notes.brief != nil {
            Section {
                DisclosureGroup("Call details") {
                    if notes.automaticSummary != nil {
                        ForEach(Array(notes.summary.enumerated()), id: \.offset) { _, line in Text(line) }
                    }
                    if let brief = notes.brief {
                        Text("Your request").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                        Text(brief)
                    }
                }
            }
        }
    }
}

/// One summary presentation for just-ended and saved calls. Missing AI text never
/// hides the transcript or makes recorded call details look like an AI summary.
struct CallSummaryContent: View {
    let notes: CallNotes?
    var awaitingSummary = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let summary = notes?.automaticSummary {
                Text(summary).accessibilityIdentifier("notes.bolnaSummary")
                Text("Automatic summary · read the transcript for exact words.")
                    .font(.caption).foregroundStyle(.secondary)
            } else {
                Text(availability).font(.subheadline).foregroundStyle(.secondary)
                    .accessibilityIdentifier("notes.summaryAvailability")
                if let notes {
                    ForEach(Array(notes.summary.enumerated()), id: \.offset) { _, line in
                        Text(line)
                    }
                    if !notes.summary.isEmpty {
                        Text("From the recorded call details.").font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
        }
        .textSelection(.enabled)
    }

    private var availability: String {
        if notes?.outcome == "no_answer" { return "No one answered, so there is no conversation to summarize." }
        if awaitingSummary { return "The automatic summary is being prepared. You can already read the transcript below." }
        return "An automatic summary is not available for this call. The saved call details are shown below."
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
