import SwiftUI

/// The large full-width buttons (CALL, Start call, SEND, STOP) that the user
/// must be able to hit easily with the phone propped an arm away.
struct BigActionButtonStyle: ButtonStyle {
    var tint: Color
    var foreground: Color = .white

    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.title2.bold())
            .multilineTextAlignment(.center)
            .foregroundStyle(isEnabled ? foreground : .secondary)
            .frame(maxWidth: .infinity, minHeight: 64)
            .padding(.horizontal, 12)
            .background(
                isEnabled ? tint : Color.gray.opacity(0.25),
                in: RoundedRectangle(cornerRadius: 16, style: .continuous)
            )
            .opacity(configuration.isPressed ? 0.8 : 1)
            .contentShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
    }
}

extension ButtonStyle where Self == BigActionButtonStyle {
    static func bigAction(_ tint: Color, foreground: Color = .white) -> BigActionButtonStyle {
        BigActionButtonStyle(tint: tint, foreground: foreground)
    }
}
