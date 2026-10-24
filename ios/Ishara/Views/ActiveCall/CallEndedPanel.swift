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
            if reason == .hangUpUnconfirmed {
                Label("Couldn't confirm the hang-up. Check the call is over.",
                      systemImage: "exclamationmark.triangle.fill")
                    .font(.headline)
                    .foregroundStyle(.orange)
                    .multilineTextAlignment(.center)
            }
            Text("Nothing more will be sent. Any unsent draft was wiped.")
                .font(.body)
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
        }
        .padding(24)
        .frame(maxWidth: .infinity)
        .background(.background.secondary, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("call.endedPanel")
    }

    private var title: String {
        switch reason {
        case .userEnded, .hangUpUnconfirmed: "You ended the call"
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
    /// False once the app has stopped trying, so it doesn't promise a reconnect.
    let isReconnecting: Bool

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "wifi.exclamationmark")
                .font(.system(size: 48))
                .foregroundStyle(.secondary)
                .accessibilityHidden(true)
            Text(ActiveCallViewModel.connectionLostTitle)
                .font(.title2.bold())
            Text(isReconnecting
                 ? "\(notice). Chips and draft were wiped. Reconnecting… You can still End the call."
                 : "\(notice). Nothing will be sent. End the call to go back.")
                .font(.body)
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
        }
        .padding(24)
        .frame(maxWidth: .infinity)
        .background(.background.secondary, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("call.connectionLostPanel")
    }
}

#Preview {
    VStack {
        ConnectionLostPanel(notice: "Nothing will be sent", isReconnecting: true)
        ConnectionLostPanel(notice: "The backend no longer knows this call", isReconnecting: false)
        CallEndedPanel(reason: .userEnded)
        CallEndedPanel(reason: .hangUpUnconfirmed)
        CallEndedPanel(reason: .failed("Connection lost"))
    }
    .padding()
}
