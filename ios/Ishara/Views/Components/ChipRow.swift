import CallSession
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
                Text(chip.label)
                    .font(.body.weight(.semibold))
                Image(systemName: "xmark")
                    .font(.caption.weight(.bold))
                    .accessibilityHidden(true)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .foregroundStyle(chip.sign == nil ? .white : .black)
            .background(chip.sign == nil ? Color.red : Color.green.opacity(0.75), in: Capsule())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(accessibilityLabel)
        .accessibilityHint("Double tap to remove")
    }

    private var accessibilityLabel: String {
        if let sign = chip.sign {
            "Recognised sign: \(sign.rawValue)"
        } else {
            "Unsure sign. It will not be sent. Try again."
        }
    }
}

#Preview {
    ChipRow(chips: [
        .recognised(.no),
        .recognised(.afternoon),
        .recognised(.morning),
        .unsure(),
    ], onRemove: { _ in })
    .padding()
}
