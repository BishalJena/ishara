import SwiftUI

/// The sentence that SEND would speak, with a badge saying who wrote it.
struct DraftCard: View {
    let draft: DraftDisplay?

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
        guard let draft else { return "No draft yet" }
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
        }
    }
}

#Preview {
    VStack {
        DraftCard(draft: DraftDisplay(text: "No, sorry, 4 pm doesn't work. Is there anything tomorrow morning?", badge: .llm))
        DraftCard(draft: DraftDisplay(text: "No. In the morning, please.", badge: .template))
        DraftCard(draft: nil)
    }
    .padding()
}
