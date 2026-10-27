import CallSession
import SwiftUI

/// Decision D8 pick-one: the model is fairly but not fully sure of a sign. It becomes a chip
/// (or answers the agent's question) only if the user taps it; nothing is spoken by itself.
struct CandidateTile: View {
    let sign: Sign
    let onAccept: () -> Void
    let onDismiss: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            Button(action: onAccept) {
                HStack(spacing: 8) {
                    Image(systemName: "hand.raised.fingers.spread")
                        .accessibilityHidden(true)
                    Text("Did you mean ") + Text(sign.rawValue.uppercased()).bold() + Text("?")
                    Spacer(minLength: 0)
                    Text("Use it")
                        .font(.subheadline.weight(.semibold))
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .buttonStyle(.bordered)
            .tint(.green)
            .controlSize(.large)
            .accessibilityLabel("Did you mean \(sign.rawValue)? Double tap to use it.")
            .accessibilityIdentifier("candidate.accept")

            Button(action: onDismiss) {
                Image(systemName: "xmark")
                    .font(.headline)
            }
            .buttonStyle(.bordered)
            .controlSize(.large)
            .accessibilityLabel("No, sign again")
            .accessibilityIdentifier("candidate.dismiss")
        }
    }
}

/// Shown after a `?` that happened because a hand left the picture during the sign.
struct FramingHint: View {
    var body: some View {
        Label("A hand left the picture. Keep both hands inside the frame and sign again.",
              systemImage: "rectangle.dashed")
            .font(.subheadline)
            .foregroundStyle(.orange)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityIdentifier("call.framingHint")
    }
}

#Preview {
    VStack(spacing: 16) {
        CandidateTile(sign: .tomorrow, onAccept: {}, onDismiss: {})
        FramingHint()
    }
    .padding()
}
