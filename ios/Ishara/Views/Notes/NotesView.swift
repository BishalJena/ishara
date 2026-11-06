import CallSession
import SwiftUI

/// The call summary, next step and expandable transcript. The model loads and follows
/// the canonical presentation while this screen displays it.
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
            .navigationTitle("Call summary")
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
        if notes.presentation?.status != "ready" && (!notes.openQuestions.isEmpty || !notes.followUps.isEmpty) {
            Section("What needs your attention") {
                ForEach(attentionLines, id: \.self) {
                    Label($0, systemImage: "questionmark.circle").foregroundStyle(.orange)
                }
            }
        }
        Section {
            CallSummaryDisclosure("Transcript (\(notes.transcript.count) lines)", identifier: "notes.transcript") {
                if notes.transcript.isEmpty { Text("No transcript was captured for this call.").foregroundStyle(.secondary) }
                ForEach(Array(notes.transcript.enumerated()), id: \.offset) { _, entry in
                    TranscriptRow(speaker: entry.speaker == .agent ? "Agent (for you)" : "They said",
                                  text: entry.text, isAgent: entry.speaker == .agent)
                }
            }
        }
        if !notes.summary.isEmpty || notes.brief != nil {
            Section {
                CallSummaryDisclosure("Call details", identifier: "notes.details") {
                    if !notes.summary.isEmpty {
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

/// A single accessible toggle keeps the disclosure chevron out of the button tree.
/// The default List disclosure exposes a separate unnamed chevron button on iOS 26.
struct CallSummaryDisclosure<Content: View>: View {
    let title: String
    let identifier: String
    let systemImage: String?
    let font: Font
    let content: Content
    @State private var expanded = false

    init(_ title: String, identifier: String, systemImage: String? = nil, font: Font = .body,
         @ViewBuilder content: () -> Content) {
        self.title = title
        self.identifier = identifier
        self.systemImage = systemImage
        self.font = font
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Button { expanded.toggle() } label: {
                HStack {
                    if let systemImage { Label(title, systemImage: systemImage) } else { Text(title) }
                    Spacer()
                    Image(systemName: expanded ? "chevron.down" : "chevron.right")
                        .imageScale(.small).foregroundStyle(.secondary).accessibilityHidden(true)
                }
                .font(font).frame(minHeight: 44).contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(title)
            .accessibilityValue(expanded ? "Expanded" : "Collapsed")
            .accessibilityIdentifier(identifier)
            if expanded { content }
        }
    }
}

/// One glanceable presentation for just-ended and saved calls.
struct CallSummaryContent: View {
    let notes: CallNotes?
    var awaitingSummary = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let notes {
                Text(notes.summaryTitle).font(.title3.weight(.semibold))
                    .accessibilityIdentifier("notes.taskTitle")
                Text(notes.summaryOverview).accessibilityIdentifier(notes.presentation?.status == "ready" ? "notes.summaryOverview" : "notes.summaryPendingOverview")
                ForEach(Array((notes.presentation?.keyPoints ?? []).prefix(3).enumerated()), id: \.offset) { _, point in
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text("•").foregroundStyle(.secondary)
                        Text(point)
                    }.font(.subheadline)
                }
                if let next = notes.presentation?.nextStep, !next.isEmpty {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Next step").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                        Text(next).font(.subheadline)
                    }.accessibilityIdentifier("notes.nextStep")
                }
            }
            if awaitingSummary {
                Text("Preparing the call summary…").font(.subheadline).foregroundStyle(.secondary)
                    .accessibilityIdentifier("notes.summaryAvailability")
            } else if notes == nil {
                Text("No summary is available for this call.").foregroundStyle(.secondary)
            }
        }
        .textSelection(.enabled)
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
