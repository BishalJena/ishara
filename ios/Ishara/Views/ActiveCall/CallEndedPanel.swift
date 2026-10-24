import SwiftUI

/// Shown after End, a hang-up or a lost connection. Nothing more is sent.
struct CallEndedPanel: View {
    let reason: ActiveCallViewModel.EndReason

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: iconName)
                .font(.system(size: 48))
                .foregroundStyle(.secondary)
                .accessibilityHidden(true)
            Text(title)
                .font(.title2.bold())
                .multilineTextAlignment(.center)
            Text("Nothing will be sent. Any pending draft was wiped, so the next call starts clean.")
                .font(.body)
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
        }
        .padding(24)
        .frame(maxWidth: .infinity)
        .background(.background.secondary, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .accessibilityElement(children: .combine)
    }

    private var title: String {
        switch reason {
        case .userEnded: "You ended the call"
        case .remoteEnded: "The call ended"
        case .failed(let message): message
        }
    }

    private var iconName: String {
        if case .failed = reason { "wifi.exclamationmark" } else { "phone.down.fill" }
    }
}

#Preview {
    VStack {
        CallEndedPanel(reason: .userEnded)
        CallEndedPanel(reason: .failed("Connection lost"))
    }
    .padding()
}
