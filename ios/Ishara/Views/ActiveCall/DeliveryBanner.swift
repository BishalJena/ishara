import SwiftUI

/// Result of the last SEND: delivered, or not delivered with a manual retry.
struct DeliveryBanner: View {
    let delivery: ActiveCallViewModel.Delivery

    var body: some View {
        switch delivery {
        case .delivered:
            banner(
                title: "✓ Delivered",
                detail: "Chips and draft were wiped, so old text can't replay.",
                color: .green
            )
        case .notDelivered:
            // The sentence itself is not repeated here: the draft card below shows
            // exactly what SEND will speak, and repeating it pushed that card off screen.
            banner(
                title: "Not delivered — tap SEND again",
                detail: "Your last reply was not spoken. Nothing is resent unless you tap SEND.",
                color: .orange
            )
        case .idle, .speaking:
            EmptyView()
        }
    }

    private func banner(title: String, detail: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.headline)
            Text(detail)
                .font(.subheadline)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.horizontal)
        .padding(.vertical, 10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(color.opacity(0.2), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(color, lineWidth: 1.5))
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("call.deliveryBanner")
    }
}

#Preview {
    VStack {
        DeliveryBanner(delivery: .delivered)
        DeliveryBanner(delivery: .notDelivered(text: "No, sorry. Is tomorrow morning possible?"))
    }
    .padding()
}
