import SwiftUI

/// Screens 3 and 4: signing a reply, then speaking it. Also shows the ended state.
struct ActiveCallView: View {
    let model: ActiveCallViewModel
    let onLeave: () -> Void

    /// Grows with Dynamic Type so a whole caption still fits at large sizes, but is
    /// capped so the chips, draft and SEND keep most of the screen.
    @ScaledMetric(relativeTo: .body) private var captionHeight: CGFloat = 150

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
                .frame(height: min(captionHeight, 240))

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
        } else if case .speaking(_, let draft) = model.delivery {
            SpeakingPanel(text: draft.text, cameraState: model.cameraState,
                          isStopRequested: model.isStopRequested)
        } else {
            SigningPanel(model: model)
        }
    }
}

/// Quick replies + Clear + SEND while signing, STOP while speaking, Back to Home
/// once ended. Quick replies sit here, not in the scrolling panel, so a long draft
/// or a delivery banner can't push them out of sight.
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
            VStack(spacing: 12) {
                QuickReplyBar(onChoose: model.choose)
                    .disabled(!model.canUseQuickReplies)
                sendRow
            }
        }
    }

    private var sendRow: some View {
        HStack(spacing: 12) {
            Button("Clear", action: model.clear)
                .buttonStyle(.bigAction(Color.gray.opacity(0.3), foreground: .primary))
                // Sized to its label so the word never wraps at large text sizes;
                // SEND takes the remaining width.
                .fixedSize(horizontal: true, vertical: false)
                .disabled(model.chips.isEmpty && model.draft == nil)
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
