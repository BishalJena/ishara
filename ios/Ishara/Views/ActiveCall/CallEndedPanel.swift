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

/// The socket dropped mid-call. Nothing is sent while it's down; the app reconnects.
struct ConnectionLostPanel: View {
    let notice: String

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "wifi.exclamationmark")
                .font(.system(size: 48))
                .foregroundStyle(.secondary)
                .accessibilityHidden(true)
            Text(ActiveCallViewModel.connectionLostTitle)
                .font(.title2.bold())
            Text("\(notice). Chips and draft were wiped. Reconnecting… You can still End the call.")
                .font(.body)
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
        }
        .padding(24)
        .frame(maxWidth: .infinity)
        .background(.background.secondary, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .accessibilityElement(children: .combine)
    }
}

#Preview {
    VStack {
        ConnectionLostPanel(notice: "Nothing will be sent")
        CallEndedPanel(reason: .userEnded)
        CallEndedPanel(reason: .failed("Connection lost"))
    }
    .padding()
}
