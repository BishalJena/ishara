import CallSession
import SwiftUI

/// The receptionist's words and the user's delivered replies, newest at the bottom.
struct CaptionHistory: View {
    let captions: [Caption]

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 10) {
                    if captions.isEmpty {
                        Text("The receptionist's words will appear here.")
                            .font(.callout)
                            .foregroundStyle(.secondary)
                    }
                    // Captions are only appended (or all wiped), so the position is a stable id.
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
        VStack(alignment: .leading, spacing: 2) {
            Text(entry.speaker == .receptionist ? "Receptionist" : "You")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            Text(entry.text)
                .font(entry.speaker == .receptionist ? .title3.weight(.semibold) : .body)
                .foregroundStyle(entry.speaker == .receptionist ? .primary : .secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier(entry.speaker == .receptionist ? "caption.receptionist" : "caption.you")
    }
}

#Preview {
    CaptionHistory(captions: [
        Caption(text: "Hello, I'd like a doctor's appointment tomorrow.", at: .now, speaker: .user),
        Caption(text: "We have 4 pm tomorrow. Does that work?", at: .now),
    ])
    .frame(height: 160)
    .padding()
}
