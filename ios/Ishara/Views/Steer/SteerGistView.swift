import CallSession
import SwiftUI

/// The gist after a steer call: the outcome in one line, what was decided and shared, the
/// follow-ups the receptionist asked for, how much the user stepped in, and the transcript.
/// Every detail comes from the backend's notes, which quote the transcript.
struct SteerGistView: View {
    let model: NotesModel
    let onDone: () -> Void

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    if let notes = model.notes {
                        outcome(notes)
                        if !notes.summary.isEmpty { summary(notes) }
                        if !notes.followUps.isEmpty { followUps(notes) }
                        if let bolna = notes.bolnaSummary { card("Call summary", symbol: "text.quote") { Text(bolna) } }
                        transcript(notes)
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
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done", action: onDone).accessibilityIdentifier("notes.done")
                }
                ToolbarItem(placement: .topBarLeading) {
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
                .font(.title2.weight(.bold))
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
        default: "You stepped in \(notes.steppedIn) times; Ishara handled the rest."
        }
    }

    private func summary(_ notes: CallNotes) -> some View {
        card("The gist", symbol: "list.bullet") {
            ForEach(notes.summary, id: \.self) { line in
                HStack(alignment: .top, spacing: 8) {
                    Image(systemName: line.hasPrefix("You") ? "keyboard" : "message.square.quote").imageScale(.small)
                        .foregroundStyle(.secondary).padding(.top, 3)
                    Text(line)
                }
            }
        }
    }

    private func followUps(_ notes: CallNotes) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(notes.followUps.count == 1 ? "1 follow-up" : "\(notes.followUps.count) follow-ups", systemImage: "bookmark.fill")
                .font(.headline).foregroundStyle(.orange)
            ForEach(notes.followUps, id: \.self) { asked in
                VStack(alignment: .leading, spacing: 4) {
                    Text("They asked: “\(asked)”").font(.subheadline.weight(.semibold))
                    Text("Ishara said you'd send it afterwards. It never guesses a detail you didn't give.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }
        }
        .padding(16).frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.orange.opacity(0.12), in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        .accessibilityIdentifier("notes.followUps")
    }

    private func transcript(_ notes: CallNotes) -> some View {
        DisclosureGroup {
            VStack(alignment: .leading, spacing: 12) {
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
            Label("Full transcript (\(notes.transcript.count) lines)", systemImage: "text.alignleft").font(.headline)
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
