import SwiftUI

/// The sentence that SEND would speak, with a badge saying who wrote it.
struct DraftCard: View {
    let draft: DraftDisplay?
    /// Chips are on screen and their draft is on its way; don't ask the user to sign again.
    var isComposing = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Draft")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.secondary)
                Spacer()
                if let draft {
                    SourceBadge(badge: draft.badge)
                }
            }
            if let draft {
                Text("\u{201C}\(draft.text)\u{201D}")
                    .font(.title3)
                    .fixedSize(horizontal: false, vertical: true)
            } else if isComposing {
                HStack(spacing: 8) {
                    ProgressView()
                    Text("Composing…")
                        .font(.body)
                        .foregroundStyle(.secondary)
                }
            } else {
                Text("Sign your reply or pick a quick reply.")
                    .font(.body)
                    .foregroundStyle(.secondary)
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.background.secondary, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .accessibilityElement(children: .combine)
        .accessibilityLabel(accessibilityLabel)
        .accessibilityIdentifier("call.draft")
    }

    private var accessibilityLabel: String {
        guard let draft else { return isComposing ? "Composing the draft" : "No draft yet" }
        return "Draft from \(draft.badge.title): \(draft.text)"
    }
}

struct SourceBadge: View {
    let badge: DraftBadge

    var body: some View {
        Text(badge.title)
            .font(.caption.weight(.bold))
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .foregroundStyle(.white)
            .background(color, in: Capsule())
    }

    private var color: Color {
        switch badge {
        case .llm: .purple
        case .template: .blue
        case .quickReply: .teal
        case .notDelivered: .orange
        case .stopped: .gray
        }
    }
}

#Preview {
    VStack {
        DraftCard(draft: DraftDisplay(text: "No, sorry, 4 pm doesn't work. Is there anything tomorrow morning?", badge: .llm))
        DraftCard(draft: DraftDisplay(text: "No. In the morning, please.", badge: .template))
        DraftCard(draft: nil, isComposing: true)
        DraftCard(draft: nil)
    }
    .padding()
}
