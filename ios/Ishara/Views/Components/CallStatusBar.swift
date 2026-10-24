import SwiftUI

/// Contact, call state and elapsed time, with End always in reach.
struct CallStatusBar: View {
    let contactName: String
    let phase: ActiveCallViewModel.Phase
    let isSpeaking: Bool
    let connectedAt: Date?
    let onEnd: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(contactName)
                    .font(.headline)
                statusLine
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier("call.status")

            if !isEnded {
                Button("End", role: .destructive, action: onEnd)
                    .buttonStyle(.borderedProminent)
                    .tint(.red)
                    .controlSize(.large)
                    .accessibilityLabel("End call")
                    .accessibilityIdentifier("call.end")
            }
        }
        .padding(12)
        .background(.background.secondary, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    @ViewBuilder
    private var statusLine: some View {
        switch phase {
        case .connecting(let status):
            Text(status == .ringing ? "Ringing…" : "Dialing…")
        case .interrupted:
            Text("Connection lost · reconnecting…")
        case .live:
            if let connectedAt {
                TimelineView(.periodic(from: connectedAt, by: 1)) { context in
                    Text("\(isSpeaking ? "Speaking" : "In call") · \(elapsed(since: connectedAt, at: context.date))")
                }
            } else {
                Text("In call")
            }
        case .ended:
            Text("Call ended")
        }
    }

    private var isEnded: Bool {
        if case .ended = phase { true } else { false }
    }

    private func elapsed(since start: Date, at now: Date) -> String {
        let seconds = max(0, Int(now.timeIntervalSince(start)))
        return Duration.seconds(seconds).formatted(.time(pattern: .minuteSecond))
    }
}

#Preview {
    CallStatusBar(contactName: "City Clinic", phase: .live, isSpeaking: false,
                  connectedAt: .now.addingTimeInterval(-102), onEnd: {})
        .padding()
}
