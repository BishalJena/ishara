import CallSession
import SwiftUI

/// The receptionist's words, the call agent's fixed lines and the user's delivered
/// replies, newest at the bottom.
/// Captions are kept after the call as a read-only transcript.
struct CaptionHistory: View {
    let captions: [Caption]
    /// True once the call is over, so an empty feed says there was nothing rather than
    /// promising words that won't come.
    var isCallOver = false

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 10) {
                    if captions.isEmpty {
                        Text(isCallOver ? "No captions in this call." : "The receptionist's words will appear here.")
                            .font(.callout)
                            .foregroundStyle(.secondary)
                            .accessibilityIdentifier("caption.placeholder")
                    }
                    // Captions are only ever appended, so the position is a stable id.
                    ForEach(Array(captions.enumerated()), id: \.offset) { index, entry in
                        CaptionRow(entry: entry)
                            .id(index)
                    }
                }
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            // Opens on the newest caption even when the history already has entries
            // (for example after returning to the screen); onChange only sees later ones.
            .defaultScrollAnchor(.bottom)
            .onChange(of: captions.count) { _, count in
                guard count > 0 else { return }
                withAnimation { proxy.scrollTo(count - 1, anchor: .bottom) }
            }
        }
        .background(Color.teal.opacity(0.15), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .accessibilityLabel("Conversation captions")
    }
}

private struct CaptionRow: View {
    let entry: Caption

    var body: some View {
        switch entry.speaker {
        case .receptionist:
            line(label: "Receptionist", font: .title3.weight(.semibold), style: .primary)
                .accessibilityIdentifier("caption.receptionist")
        case .user:
            line(label: "You", font: .body, style: .secondary)
                .accessibilityIdentifier("caption.you")
        case .agent:
            // Said by the call agent without a SEND (disclosure, holding line, goodbye):
            // set apart on the right in a quieter style so it never reads as a reply.
            line(label: "Ishara (voice)", font: .callout.italic(), style: .secondary, alignment: .trailing)
                .accessibilityLabel("Ishara voice, said automatically: \(entry.text)")
                .accessibilityIdentifier("caption.agent")
        }
    }

    private func line(label: String, font: Font, style: HierarchicalShapeStyle,
                      alignment: HorizontalAlignment = .leading) -> some View {
        VStack(alignment: alignment, spacing: 2) {
            Text(label)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            Text(entry.text)
                .font(font)
                .foregroundStyle(style)
                .multilineTextAlignment(alignment == .trailing ? .trailing : .leading)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: alignment == .trailing ? .trailing : .leading)
        .padding(.leading, alignment == .trailing ? 32 : 0)
        .accessibilityElement(children: .combine)
    }
}

#Preview {
    CaptionHistory(captions: [
        Caption(text: "Hello, I'm calling for a Deaf caller who is using Ishara.", at: .now, speaker: .agent),
        Caption(text: "Hello, I'd like a doctor's appointment tomorrow.", at: .now, speaker: .user),
        Caption(text: "We have 4 pm tomorrow. Does that work?", at: .now),
    ])
    .frame(height: 160)
    .padding()
}
