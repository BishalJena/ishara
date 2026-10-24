import SwiftUI

/// Yes / No / Wait / Repeat. Each puts a full sentence in the draft; SEND is still needed.
struct QuickReplyBar: View {
    let onChoose: (QuickReply) -> Void

    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 8) { buttons }
            // At large text sizes the row scrolls sideways rather than wrapping into
            // a 2x2 grid, which took so much height that the draft disappeared
            // behind the action bar.
            ScrollView(.horizontal) {
                HStack(spacing: 8) { buttons }
            }
            .scrollIndicators(.visible)
        }
    }

    private var buttons: some View {
        ForEach(QuickReply.allCases) { reply in
            Button { onChoose(reply) } label: {
                // Fixed to one line: an even 4-way split is narrower than "Repeat"
                // needs, and a wrapped label turns the button into a tall blob.
                // When the labels can't fit, ViewThatFits switches to the scrolling row.
                Text(reply.label)
                    .lineLimit(1)
                    .fixedSize()
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
            .controlSize(.large)
            .accessibilityIdentifier("quickReply.\(reply.id)")
            .accessibilityHint("Puts \u{201C}\(reply.sentence)\u{201D} in the draft")
        }
    }
}

#Preview {
    QuickReplyBar { _ in }
        .padding()
}
