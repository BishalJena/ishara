import SwiftUI

/// What the call screen is showing. The scrolling panel and the action bar both follow it,
/// so the sentence SEND or STOP acts on always sits in the bar right next to that button.
enum ActiveCallStage: Equatable {
    /// Signing a reply: the draft sits above SEND.
    case signing
    /// The sentence being spoken sits above STOP.
    case speaking(text: String)
    case connectionLost(notice: String, isReconnecting: Bool)
    case ended(ActiveCallViewModel.EndReason)

    @MainActor
    init(_ model: ActiveCallViewModel) {
        switch model.phase {
        case .ended(let reason): self = .ended(reason)
        case .interrupted(let notice): self = .connectionLost(notice: notice, isReconnecting: true)
        case .disconnected(let reason): self = .connectionLost(notice: reason, isReconnecting: false)
        case .connecting, .live:
            if case .speaking(let text) = model.delivery {
                self = .speaking(text: text)
            } else {
                self = .signing
            }
        }
    }
}

/// Screens 3 and 4: signing a reply, then speaking it. Also shows the ended state.
struct ActiveCallView: View {
    let model: ActiveCallViewModel
    let onLeave: () -> Void
    /// D9: opens the call's notes once it has ended.
    var onShowNotes: (() -> Void)? = nil

    /// Grows with Dynamic Type so a whole caption still fits at large sizes, but is
    /// capped so the chips, draft and SEND keep most of the screen.
    @ScaledMetric(relativeTo: .body) private var captionHeight: CGFloat = 150
    /// Heights of the whole screen and of the action bar. Neither depends on the caption
    /// box, so sizing the captions from them can't feed back into a layout loop.
    @State private var screenHeight: CGFloat?
    @State private var actionBarHeight: CGFloat?

    private var stage: ActiveCallStage { ActiveCallStage(model) }

    /// At large text sizes the action bar (draft or spoken sentence plus buttons) takes
    /// much of the screen; the captions then give up space so the chips stay reachable.
    private var captionBoxHeight: CGFloat {
        let preferred = min(captionHeight, 240)
        guard let screenHeight, let actionBarHeight else { return preferred }
        return max(80, min(preferred, (screenHeight - actionBarHeight) * 0.4))
    }

    /// Room for the pinned sentence in the action bar. Past this it scrolls inside its
    /// card, which only happens for very long sentences at the largest text sizes.
    private var sentenceMaxHeight: CGFloat {
        (screenHeight ?? 800) * 0.55
    }

    var body: some View {
        VStack(spacing: 12) {
            CallStatusBar(
                contactName: model.setup.contact.name,
                phase: model.phase,
                isSpeaking: model.isSpeaking,
                connectedAt: model.connectedAt,
                onEnd: model.end
            )
            CaptionHistory(captions: model.captions, isCallOver: model.isCallOver)
                .frame(height: captionBoxHeight)

            ScrollViewReader { proxy in
                ScrollView {
                    content
                        .padding(.bottom, 8)
                }
                .scrollBounceBehavior(.basedOnSize)
                // At large text sizes the action bar leaves too little room for the camera
                // and the chips together; keep the chips in view so a wrong one can be
                // removed before SEND.
                .onChange(of: model.chips) { proxy.scrollTo(SigningPanel.chipRowID, anchor: .bottom) }
                .onChange(of: actionBarHeight) { proxy.scrollTo(SigningPanel.chipRowID, anchor: .bottom) }
            }
        }
        .padding(.horizontal)
        .padding(.top, 8)
        .safeAreaInset(edge: .bottom) {
            CallActionBar(model: model, stage: stage, sentenceMaxHeight: sentenceMaxHeight, onLeave: onLeave,
                          onShowNotes: onShowNotes)
                .padding()
                .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { actionBarHeight = $0 }
                .background(.bar)
        }
        .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { screenHeight = $0 }
        // Past AX-XL the status bar, a whole sentence and SEND or STOP no longer fit on
        // an iPhone 17e together, so the call screen stops growing there.
        .dynamicTypeSize(...DynamicTypeSize.accessibility3)
        .animation(.default, value: model.isSpeaking)
        .animation(.default, value: model.isEnded)
        .task { await model.run() }
    }

    @ViewBuilder
    private var content: some View {
        switch stage {
        case .ended(let reason):
            CallEndedPanel(reason: reason)
        case .connectionLost(let notice, let isReconnecting):
            ConnectionLostPanel(notice: notice, isReconnecting: isReconnecting)
        case .speaking:
            SpeakingPanel(cameraState: model.cameraState, camera: model.recognition.camera,
                          isStopTooLate: model.isStopTooLate, errorMessage: model.errorMessage)
        case .signing:
            SigningPanel(model: model)
        }
    }
}

/// Draft + quick replies + Clear + SEND while signing, the spoken sentence + STOP while
/// speaking, Back to Home once ended. The sentence lives here, not in the scrolling
/// panel, so it can never be scrolled away or hidden behind the button that speaks
/// or stops it, at any text size.
private struct CallActionBar: View {
    let model: ActiveCallViewModel
    let stage: ActiveCallStage
    let sentenceMaxHeight: CGFloat
    let onLeave: () -> Void
    let onShowNotes: (() -> Void)?

    var body: some View {
        if model.isDelegated {
            delegatedBar
        } else {
            liveBar
        }
    }

    /// D9: no draft, quick replies or SEND; the agent speaks from the approved brief. The
    /// user answers its questions (attended) and reads the notes afterwards.
    @ViewBuilder
    private var delegatedBar: some View {
        switch stage {
        case .ended, .connectionLost(_, false):
            VStack(spacing: 12) {
                if let onShowNotes {
                    Button(action: onShowNotes) {
                        Label("See the call notes", systemImage: "doc.text")
                    }
                    .buttonStyle(.bigAction(.blue))
                    .accessibilityIdentifier("call.notes")
                }
                Button("Back to Home", action: onLeave)
                    .buttonStyle(.bigAction(Color.gray.opacity(0.3), foreground: .primary))
                    .accessibilityIdentifier("call.backHome")
            }
        case .signing, .speaking, .connectionLost:
            if let question = model.openQuestion {
                // Leaves room for the answer buttons and the status bar with End above.
                AskCard(question: question, detailsMaxHeight: sentenceMaxHeight * 0.5, onAnswer: model.answer)
            }
        }
    }

    @ViewBuilder
    private var liveBar: some View {
        switch stage {
        case .ended:
            Button("Back to Home", action: onLeave)
                .buttonStyle(.bigAction(.blue))
                .accessibilityIdentifier("call.backHome")
        case .speaking(let text):
            VStack(spacing: 12) {
                PinnedSentence(maxHeight: sentenceMaxHeight) {
                    // Once STOP is refused it is still being spoken, not stopping.
                    SpeakingCard(text: text, isStopRequested: model.isStopRequested && !model.isStopTooLate)
                }
                Button(action: model.stop) {
                    Label("STOP", systemImage: "stop.fill")
                }
                .buttonStyle(.bigAction(.red))
                .disabled(model.isStopRequested)
                .accessibilityHint("Cancels the reply if it has not been spoken yet")
                .accessibilityIdentifier("call.stop")
            }
        case .signing:
            VStack(spacing: 12) {
                if let question = model.openQuestion {
                    AskCard(question: question, onAnswer: model.answer)
                }
                QuickReplyBar(onChoose: model.choose)
                    .disabled(!model.canUseQuickReplies)
                PinnedSentence(maxHeight: sentenceMaxHeight) {
                    DraftCard(draft: model.draft, isComposing: model.isComposing)
                }
                sendRow
            }
        case .connectionLost:
            // Pending drafts are wiped when the connection drops, so there is no
            // sentence to show; the disabled controls keep the layout steady.
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
                .accessibilityIdentifier("call.clear")
            Button(action: model.send) {
                Label("SEND", systemImage: "paperplane.fill")
            }
            .buttonStyle(.bigAction(.orange))
            .disabled(!model.canSend)
            .accessibilityLabel("Send reply")
            .accessibilityHint("Speaks the draft into the call")
            .accessibilityIdentifier("call.send")
        }
    }
}

/// Shows the sentence at its natural height when it fits in `maxHeight`, and only
/// otherwise lets it scroll inside the bar, so the buttons below it stay on screen.
struct PinnedSentence<Content: View>: View {
    let maxHeight: CGFloat
    @ViewBuilder let content: Content

    @State private var contentHeight: CGFloat?

    var body: some View {
        ScrollView {
            content
                .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { contentHeight = $0 }
        }
        .scrollBounceBehavior(.basedOnSize)
        .scrollIndicators(.visible)
        // A ScrollView takes all the height it is offered; pin it to the content instead.
        .frame(height: min(contentHeight ?? maxHeight, maxHeight))
    }
}
