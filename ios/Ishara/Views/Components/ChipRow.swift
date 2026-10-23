import SwiftUI

/// Recognised signs (green, ✕ removes) and unsure ones (red [?], never sent).
struct ChipRow: View {
    let chips: [Chip]
    let onRemove: (Chip) -> Void

    var body: some View {
        if chips.isEmpty {
            Text("Signs you make appear here.")
                .font(.callout)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
        } else {
            FlowLayout(spacing: 8) {
                ForEach(chips) { chip in
                    ChipView(chip: chip) { onRemove(chip) }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

struct ChipView: View {
    let chip: Chip
    let onRemove: () -> Void

    var body: some View {
        Button(action: onRemove) {
            HStack(spacing: 6) {
                Text(chip.word ?? "?")
                    .font(.body.weight(.semibold))
                Image(systemName: "xmark")
                    .font(.caption.weight(.bold))
                    .accessibilityHidden(true)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .foregroundStyle(chip.word == nil ? .white : .black)
            .background(chip.word == nil ? Color.red : Color.green.opacity(0.75), in: Capsule())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(accessibilityLabel)
        .accessibilityHint("Double tap to remove")
    }

    private var accessibilityLabel: String {
        if let word = chip.word {
            "Recognised sign: \(word)"
        } else {
            "Unsure sign. It will not be sent. Try again."
        }
    }
}

#Preview {
    ChipRow(chips: [
        Chip(kind: .recognised("no")),
        Chip(kind: .recognised("afternoon")),
        Chip(kind: .recognised("morning")),
        Chip(kind: .unsure),
    ], onRemove: { _ in })
    .padding()
}
