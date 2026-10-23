import SwiftUI

/// Screens 3 and 4: signing a reply, then speaking it. Also shows the ended state.
struct ActiveCallView: View {
    let model: ActiveCallViewModel
    let onLeave: () -> Void

    var body: some View {
        VStack(spacing: 12) {
            CallStatusBar(
                contactName: model.setup.contact.name,
                phase: model.phase,
                isSpeaking: model.isSpeaking,
                connectedAt: model.connectedAt,
                onEnd: model.end
            )
            CaptionHistory(captions: model.captions)
                .frame(height: 150)

            ScrollView {
                content
                    .padding(.bottom, 8)
            }
            .scrollBounceBehavior(.basedOnSize)
        }
        .padding(.horizontal)
        .padding(.top, 8)
        .safeAreaInset(edge: .bottom) {
            CallActionBar(model: model, onLeave: onLeave)
                .padding()
                .background(.bar)
        }
        .animation(.default, value: model.isSpeaking)
        .animation(.default, value: model.isEnded)
        .task { await model.run() }
    }

    @ViewBuilder
    private var content: some View {
        if case .ended(let reason) = model.phase {
            CallEndedPanel(reason: reason)
        } else if case .interrupted(let notice) = model.phase {
            ConnectionLostPanel(notice: notice)
        } else if case .speaking(let text) = model.delivery {
            SpeakingPanel(text: text, cameraState: model.cameraState,
                          isStopRequested: model.isStopRequested)
        } else {
            SigningPanel(model: model)
        }
    }
}

/// Clear + SEND while signing, STOP while speaking, Back to Home once ended.
private struct CallActionBar: View {
    let model: ActiveCallViewModel
    let onLeave: () -> Void

    var body: some View {
        if model.isEnded {
            Button("Back to Home", action: onLeave)
                .buttonStyle(.bigAction(.blue))
        } else if model.isSpeaking {
            Button(action: model.stop) {
                Label("STOP", systemImage: "stop.fill")
            }
            .buttonStyle(.bigAction(.red))
            .disabled(model.isStopRequested)
            .accessibilityHint("Cancels the reply if it has not been spoken yet")
        } else {
            HStack(spacing: 12) {
                Button("Clear", action: model.clear)
                    .buttonStyle(.bigAction(Color.gray.opacity(0.3), foreground: .primary))
                    .frame(maxWidth: 120)
                    .disabled(model.chips.isEmpty && model.store?.draft == nil)
                Button(action: model.send) {
                    Label("SEND", systemImage: "paperplane.fill")
                }
                .buttonStyle(.bigAction(.orange))
                .disabled(!model.canSend)
                .accessibilityLabel("Send reply")
                .accessibilityHint("Speaks the draft into the call")
            }
        }
    }
}
