import SwiftUI

/// Yes / No / Wait / Repeat. Each puts a full sentence in the draft; SEND is still needed.
struct QuickReplyBar: View {
    let onChoose: (QuickReply) -> Void

    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 8) { buttons }
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 8) { buttons }
        }
    }

    private var buttons: some View {
        ForEach(QuickReply.allCases) { reply in
            Button(reply.label) { onChoose(reply) }
                .buttonStyle(.bordered)
                .controlSize(.large)
                .frame(maxWidth: .infinity)
                .accessibilityHint("Puts \u{201C}\(reply.sentence)\u{201D} in the draft")
        }
    }
}

#Preview {
    QuickReplyBar { _ in }
        .padding()
}
