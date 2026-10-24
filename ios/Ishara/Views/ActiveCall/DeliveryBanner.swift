import SwiftUI

/// Result of the last SEND: delivered, not delivered with a manual retry, or stopped by
/// the user before it was spoken.
struct DeliveryBanner: View {
    let delivery: ActiveCallViewModel.Delivery

    var body: some View {
        switch delivery {
        case .delivered:
            StatusBanner(
                title: "✓ Delivered",
                detail: "Chips and draft were wiped, so old text can't replay.",
                color: .green
            )
        case .deliveredDespiteStop:
            // Never a plain "Delivered" after STOP: the user expected it not to be said.
            StatusBanner(
                title: "✓ Delivered — too late to stop",
                detail: "It was already being spoken when you tapped STOP. Send a correction if you need to.",
                color: .green
            )
        case .notDelivered:
            // The sentence itself is not repeated here: the draft card below shows
            // exactly what SEND will speak, and repeating it pushed that card off screen.
            StatusBanner(
                title: "Not delivered — tap SEND again",
                detail: "Your last reply was not spoken. Nothing is resent unless you tap SEND.",
                color: .orange
            )
        case .stopped:
            // A deliberate STOP is not a failure: say so, without urging a resend.
            StatusBanner(
                title: "Stopped. Nothing was spoken.",
                detail: "Tap SEND to send it anyway, or Clear.",
                color: .gray
            )
        case .idle, .speaking:
            EmptyView()
        }
    }
}

/// STOP was refused because the reply is already being spoken.
struct StopTooLateBanner: View {
    var body: some View {
        StatusBanner(
            title: "Too late to stop — it's already being spoken",
            detail: "Send a correction once it's done.",
            color: .orange,
            identifier: "call.stopTooLateBanner"
        )
    }
}

/// A backend error, in words. Errors never send anything.
struct CallErrorBanner: View {
    let message: String

    var body: some View {
        StatusBanner(title: message, detail: nil, color: .red, identifier: "call.errorBanner")
    }
}

private struct StatusBanner: View {
    let title: String
    let detail: String?
    let color: Color
    var identifier = "call.deliveryBanner"

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.headline)
                .fixedSize(horizontal: false, vertical: true)
            if let detail {
                Text(detail)
                    .font(.subheadline)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.horizontal)
        .padding(.vertical, 10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(color.opacity(0.2), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(color, lineWidth: 1.5))
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier(identifier)
    }
}

#Preview {
    VStack {
        DeliveryBanner(delivery: .delivered)
        DeliveryBanner(delivery: .deliveredDespiteStop)
        DeliveryBanner(delivery: .notDelivered(text: "No, sorry. Is tomorrow morning possible?"))
        DeliveryBanner(delivery: .stopped(text: "No, sorry. Is tomorrow morning possible?"))
        StopTooLateBanner()
        CallErrorBanner(message: "Wait until the current reply has been spoken.")
    }
    .padding()
}
