import CallSession
import SwiftUI

/// The gist after a steer call: the outcome in one line, what was decided and shared, the
/// follow-ups the receptionist asked for, how much the user stepped in, and the transcript.
/// Every detail comes from the backend's notes, which quote the transcript.
struct SteerGistView: View {
    let model: NotesModel
    let onDone: () -> Void
    let onCallAgain: () -> Void

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    if let notes = model.notes {
                        card("Call summary", symbol: "text.quote") {
                            CallSummaryContent(notes: notes, awaitingSummary: model.awaitingSummary)
                            Divider()
                            outcome(notes)
                        }
                        if !notes.followUps.isEmpty || !notes.openQuestions.isEmpty { followUps(notes) }
                        transcript(notes)
                        if notes.automaticSummary != nil && !notes.summary.isEmpty || notes.brief != nil {
                            card("Call details", symbol: "list.bullet") {
                                DisclosureGroup("Your request and recorded details") {
                                    if notes.automaticSummary != nil {
                                        ForEach(Array(notes.summary.enumerated()), id: \.offset) { _, line in Text(line) }
                                    }
                                    if let brief = notes.brief { Text(brief) }
                                }
                            }
                        }
                    } else if let failure = model.failure {
                        Label(failure, systemImage: "exclamationmark.triangle.fill").foregroundStyle(.red)
                    } else {
                        ProgressView("Wrapping up the call…").frame(maxWidth: .infinity)
                    }
                }
                .padding(20)
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("Call with \(model.contactName)")
            .navigationBarTitleDisplayMode(.inline)
            // The way out is the one big button at the bottom, where the thumb already is.
            .safeAreaInset(edge: .bottom) {
                HStack(spacing: 12) {
                    Button(action: onCallAgain) {
                        Label("Call again", systemImage: "phone.arrow.up.right")
                            .frame(maxWidth: .infinity).padding(.vertical, 6)
                    }
                    .buttonStyle(.bordered).buttonBorderShape(.capsule)
                    .accessibilityIdentifier("notes.callAgain")
                    Button(action: onDone) {
                        Text("Done").font(.headline)
                            .frame(maxWidth: .infinity).padding(.vertical, 6)
                    }
                    .buttonStyle(.borderedProminent).buttonBorderShape(.capsule)
                    .accessibilityIdentifier("notes.done")
                }
                .controlSize(.large)
                .padding(.horizontal, 20).padding(.top, 10).padding(.bottom, 6)
                .background(.bar)
            }
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { Task { await model.refresh() } } label: { Label("Refresh", systemImage: "arrow.clockwise") }
                        .disabled(model.isLoading)
                        .accessibilityIdentifier("notes.refresh")
                }
            }
        }
    }

    private func outcome(_ notes: CallNotes) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Label(NotesModel.describe(outcome: notes.outcome, ready: notes.ready), systemImage: outcomeSymbol(notes))
                .font(.headline)
                .foregroundStyle(notes.outcome == "booked" ? .green : .primary)
                .accessibilityIdentifier("notes.outcome")
            Text(steppedInText(notes)).font(.subheadline).foregroundStyle(.secondary)
        }
    }

    private func outcomeSymbol(_ notes: CallNotes) -> String {
        switch notes.outcome {
        case "booked": "checkmark.circle.fill"
        case "no_answer": "phone.down.circle.fill"
        case "callback": "arrow.uturn.left.circle.fill"
        default: "info.circle.fill"
        }
    }

    private func steppedInText(_ notes: CallNotes) -> String {
        switch notes.steppedIn {
        case 0: "Ishara handled the whole call from what you wrote."
        case 1: "You stepped in once; Ishara handled the rest."
        case 2: "You stepped in twice; Ishara handled the rest."
        default: "You stepped in \(notes.steppedIn) times; Ishara handled the rest."
        }
    }

    private func followUps(_ notes: CallNotes) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("What needs your attention", systemImage: "bookmark.fill")
                .font(.headline).foregroundStyle(.orange)
            ForEach(notes.followUps, id: \.self) { asked in
                VStack(alignment: .leading, spacing: 4) {
                    Text("They asked: “\(asked)”").font(.subheadline.weight(.semibold))
                    Text("Ishara said you'd send it afterwards. It never guesses a detail you didn't give.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }
            ForEach(notes.openQuestions.filter { !notes.followUps.contains($0) }, id: \.self) { question in
                Label(question, systemImage: "questionmark.circle").font(.subheadline)
            }
        }
        .padding(16).frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.orange.opacity(0.12), in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        .accessibilityIdentifier("notes.followUps")
    }

    private func transcript(_ notes: CallNotes) -> some View {
        DisclosureGroup {
            VStack(alignment: .leading, spacing: 12) {
                if notes.transcript.isEmpty { Text("No transcript was captured for this call.").foregroundStyle(.secondary) }
                ForEach(Array(notes.transcript.enumerated()), id: \.offset) { _, entry in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(entry.speaker == .agent ? "Ishara for you" : model.contactName)
                            .font(.caption.weight(.bold)).foregroundStyle(entry.speaker == .agent ? .purple : .secondary)
                        Text(entry.text).font(.subheadline)
                    }
                }
            }
            .padding(.top, 8)
        } label: {
            Label("Full transcript (\(notes.transcript.count) \(notes.transcript.count == 1 ? "line" : "lines"))", systemImage: "text.alignleft").font(.headline)
        }
        .padding(16)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 20, style: .continuous))
    }

    private func card<Content: View>(_ title: String, symbol: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(title, systemImage: symbol).font(.headline)
            content()
        }
        .padding(16).frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 20, style: .continuous))
    }
}
