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
            Button { onChoose(reply) } label: {
                // Fixed to one line: an even 4-way split is narrower than "Repeat"
                // needs, and a wrapped label turns the button into a tall blob.
                // When the labels can't fit, ViewThatFits switches to the grid.
                Text(reply.label)
                    .lineLimit(1)
                    .fixedSize()
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
            .controlSize(.large)
                .accessibilityHint("Puts \u{201C}\(reply.sentence)\u{201D} in the draft")
        }
    }
}

#Preview {
    QuickReplyBar { _ in }
        .padding()
}
