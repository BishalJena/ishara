import SwiftUI

/// The receptionist's words and the user's delivered replies, newest at the bottom.
struct CaptionHistory: View {
    let captions: [CaptionEntry]

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 10) {
                    if captions.isEmpty {
                        Text("The receptionist's words will appear here.")
                            .font(.callout)
                            .foregroundStyle(.secondary)
                    }
                    ForEach(captions) { entry in
                        CaptionRow(entry: entry)
                            .id(entry.id)
                    }
                }
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            // Opens on the newest caption even when the history already has entries
            // (for example after returning to the screen); onChange only sees later ones.
            .defaultScrollAnchor(.bottom)
            .onChange(of: captions.last?.id) { _, lastID in
                guard let lastID else { return }
                withAnimation { proxy.scrollTo(lastID, anchor: .bottom) }
            }
        }
        .background(Color.teal.opacity(0.15), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .accessibilityLabel("Conversation captions")
    }
}

private struct CaptionRow: View {
    let entry: CaptionEntry

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
    }
}

#Preview {
    CaptionHistory(captions: [
        CaptionEntry(speaker: .user, text: "Hello, I'd like a doctor's appointment tomorrow.", at: .now),
        CaptionEntry(speaker: .receptionist, text: "We have 4 pm tomorrow. Does that work?", at: .now),
    ])
    .frame(height: 160)
    .padding()
}
