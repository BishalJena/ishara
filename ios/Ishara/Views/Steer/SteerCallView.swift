import CallSession
import SwiftUI

/// The one call screen for steer calls: Ishara runs the call from the typed request; the
/// user watches the captions and steps in by typing (first) or signing. Each agent line
/// sits in the filling Send bar for its window; doing nothing lets it be spoken.
struct SteerCallView: View {
    @Bindable var model: ActiveCallViewModel
    let onLeave: () -> Void
    let onShowNotes: () -> Void

    @Environment(\.scenePhase) private var scenePhase
    @State private var typed = ""
    @State private var isSigning = false
    @FocusState private var typing: Bool

    var body: some View {
        VStack(spacing: 0) {
            header
            statusPill
            captions
            composer
        }
        .background(Color(.systemBackground))
        .task { await model.run() }
        .onAppear { model.setPresent(scenePhase == .active) }
        .onChange(of: scenePhase) { _, phase in model.setPresent(phase == .active) }
        .onChange(of: model.store == nil) { _, _ in model.setPresent(scenePhase == .active) }
        .onChange(of: typing) { _, isTyping in
            if isTyping { model.beginSteppingIn() } else if typed.isEmpty { model.cancelSteppingIn() }
        }
        .onChange(of: model.isCallOver) { _, isOver in if isOver { typing = false } }
    }

    // MARK: Header

    private var header: some View {
        HStack(spacing: 12) {
            Circle().fill(.blue).frame(width: 44, height: 44)
                .overlay(Text(initials).font(.headline).foregroundStyle(.white))
            VStack(alignment: .leading, spacing: 2) {
                Text(model.setup.contact.name).font(.title3.weight(.bold))
                CallTimerText(connectedAt: model.connectedAt, phase: model.phase)
                    .font(.footnote).foregroundStyle(.secondary)
            }
            Spacer()
            if model.isCallOver {
                Button("Gist", systemImage: "list.bullet.rectangle", action: onShowNotes)
                    .buttonStyle(.borderedProminent).buttonBorderShape(.capsule)
                    .accessibilityIdentifier("steer.gist")
            } else {
                Button("End", systemImage: "phone.down.fill") { model.end() }
                    .buttonStyle(.borderedProminent).buttonBorderShape(.capsule).tint(.red)
                    .accessibilityIdentifier("steer.end")
            }
        }
        .padding(.horizontal, 20).padding(.vertical, 8)
    }

    private var initials: String {
        let words = model.setup.contact.name.split(separator: " ").prefix(2)
        return words.map { String($0.prefix(1)) }.joined().uppercased()
    }

    private var statusPill: some View {
        HStack(spacing: 6) {
            Image(systemName: statusSymbol).imageScale(.small)
            Text(statusText).font(.footnote.weight(.semibold))
        }
        .padding(.vertical, 7).padding(.horizontal, 12)
        .background(statusColor.opacity(0.12), in: Capsule())
        .foregroundStyle(statusColor)
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 20)
        .accessibilityIdentifier("steer.status")
    }

    private var statusSymbol: String {
        if model.isCallOver { return "checkmark.circle.fill" }
        if model.isSteppingIn { return isSigning ? "hand.raised.fill" : "keyboard" }
        return "sparkles"
    }

    private var statusText: String {
        switch model.phase {
        case .connecting(let state): return state == .ringing ? "Ringing…" : "Calling…"
        case .interrupted(let text), .disconnected(let text): return text
        case .ended(let reason):
            switch reason {
            case .userEnded, .remoteEnded: return "Call ended"
            case .hangUpUnconfirmed: return "Ended; hang-up not confirmed"
            case .failed(let text): return text
            }
        case .live:
            if model.isSteppingIn { return isSigning ? "You're signing — Ishara waits for you" : "You're typing — Ishara is covering" }
            return "Ishara is handling it — step in any time"
        }
    }

    private var statusColor: Color {
        if model.isCallOver { return .green }
        if case .live = model.phase { return model.isSteppingIn ? .blue : .purple }
        return .secondary
    }

    // MARK: Captions

    private var captions: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 16) {
                    ForEach(Array(model.captions.enumerated()), id: \.offset) { index, caption in
                        let isLatest = index == model.captions.count - 1
                        VStack(alignment: .leading, spacing: 4) {
                            Label(speakerName(caption.speaker), systemImage: speakerSymbol(caption.speaker))
                                .font(.caption.weight(.bold))
                                .foregroundStyle(caption.speaker == .receptionist ? .secondary : speakerColor(caption.speaker))
                            Text(caption.text)
                                .font(isLatest && caption.speaker == .receptionist ? .title2.weight(.semibold) : .body)
                                .foregroundStyle(isLatest ? .primary : .secondary)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .id(index)
                        .accessibilityElement(children: .combine)
                    }
                    if let followUp = model.followUps.last {
                        Label("They asked for something you didn't give. Saved as a follow-up: “\(followUp)”", systemImage: "bookmark.fill")
                            .font(.footnote.weight(.medium))
                            .padding(10)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(Color.orange.opacity(0.12), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                            .foregroundStyle(.orange)
                            .accessibilityIdentifier("steer.followUp")
                    }
                }
                .padding(20)
            }
            .onChange(of: model.captions.count) { _, count in
                withAnimation { proxy.scrollTo(count - 1, anchor: .bottom) }
            }
        }
    }

    private func speakerName(_ speaker: Caption.Speaker) -> String {
        switch speaker {
        case .receptionist: model.setup.contact.name
        case .agent: "Ishara for you"
        case .user: "You"
        }
    }

    private func speakerSymbol(_ speaker: Caption.Speaker) -> String {
        switch speaker {
        case .receptionist: "person.wave.2"
        case .agent: "sparkles"
        case .user: isSigning ? "hand.raised.fill" : "keyboard"
        }
    }

    private func speakerColor(_ speaker: Caption.Speaker) -> Color {
        speaker == .user ? .blue : .purple
    }

    // MARK: Composer

    @ViewBuilder
    private var composer: some View {
        VStack(spacing: 10) {
            if let proposal = model.proposal {
                ProposalBar(
                    proposal: proposal,
                    onSendNow: { model.approveProposal() },
                    onEdit: {
                        if proposal.origin == .user {
                            typed = proposal.text
                            model.editPreview()
                        } else {
                            model.beginSteppingIn()
                        }
                        typing = true
                    })
            }
            if isSigning {
                signingPanel
            } else if !model.isCallOver {
                typingBar
            }
            if !model.isCallOver, !isSigning, !typing {
                Text("If you don't step in, Ishara keeps going. Nothing you type is spoken until you send it.")
                    .font(.caption2).foregroundStyle(.secondary).multilineTextAlignment(.center)
            }
        }
        .padding(.horizontal, 12).padding(.bottom, 10).padding(.top, 6)
        .background(.bar)
    }

    private var typingBar: some View {
        HStack(spacing: 8) {
            Button {
                isSigning = true
                typing = false
                model.beginSteppingIn()
            } label: {
                Image(systemName: "hand.raised.fill").frame(width: 24, height: 24)
            }
            .buttonStyle(.bordered).buttonBorderShape(.circle)
            .accessibilityLabel("Sign instead")
            .accessibilityIdentifier("steer.sign")
            .disabled(model.isCallOver)

            HStack {
                TextField("Type to step in…", text: $typed, axis: .vertical)
                    .lineLimit(1...4)
                    .focused($typing)
                    .submitLabel(.send)
                    .onSubmit(sendTyped)
                    .accessibilityIdentifier("steer.field")
                Button(action: sendTyped) {
                    Image(systemName: "arrow.up").font(.headline).frame(width: 30, height: 30)
                }
                .buttonStyle(.borderedProminent).buttonBorderShape(.circle)
                .disabled(typed.trimmingCharacters(in: .whitespaces).isEmpty || model.isCallOver)
                .accessibilityIdentifier("steer.send")
            }
            .padding(.leading, 14).padding(.trailing, 6).padding(.vertical, 6)
            .background(Color(.secondarySystemBackground), in: Capsule())
        }
    }

    private func sendTyped() {
        let text = typed.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        model.say(text)
        typed = ""
        typing = false
    }

    private var signingPanel: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 12) {
                CameraCard(camera: model.recognition.camera, state: model.cameraState)
                    .frame(width: 96, height: 128)
                    .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Text("Signs so far").font(.footnote.weight(.semibold)).foregroundStyle(.secondary)
                        Spacer()
                        Button("Type", systemImage: "keyboard") {
                            isSigning = false
                            model.clear()
                            if typed.isEmpty { model.cancelSteppingIn() }
                        }
                        .font(.footnote.weight(.semibold))
                        .accessibilityIdentifier("steer.type")
                    }
                    ChipRow(chips: model.chips, onRemove: model.removeChip)
                    if let candidate = model.candidate {
                        CandidateTile(sign: candidate, onAccept: model.acceptCandidate, onDismiss: model.dismissCandidate)
                    }
                }
            }
            if let draft = model.draft {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Ishara will say").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                    Text(draft.text).font(.body.weight(.medium))
                }
                .padding(12).frame(maxWidth: .infinity, alignment: .leading)
                .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            }
            Button {
                model.send()
            } label: {
                Label("Send", systemImage: "arrow.up").font(.headline).frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent).buttonBorderShape(.capsule).controlSize(.large)
            .disabled(!model.canSend)
            .accessibilityIdentifier("steer.sendSigned")
        }
    }
}

/// The filling Send bar: the proposed line fills from left to right over its window and is
/// spoken when full. Tap the arrow to send now, the pencil to take it over.
struct ProposalBar: View {
    let proposal: Proposal
    let onSendNow: () -> Void
    let onEdit: () -> Void

    var body: some View {
        TimelineView(.animation(minimumInterval: 1 / 30)) { context in
            let progress = proposal.progress(at: context.date)
            let remaining = max(0, proposal.windowS * (1 - progress))
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(proposal.origin == .agent
                         ? "Ishara says in \(remaining.formatted(.number.precision(.fractionLength(0)))) s · tap to edit"
                         : "Saying your line · tap to edit")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(tint)
                    Text(proposal.text).font(.subheadline.weight(.semibold))
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .contentShape(Rectangle())
                .onTapGesture(perform: onEdit)
                .accessibilityAddTraits(.isButton)
                .accessibilityLabel(proposal.origin == .agent ? "Ishara will say \(proposal.text). Tap to edit." : "Saying \(proposal.text). Tap to edit.")
                Button(action: proposal.origin == .agent ? onSendNow : onEdit) {
                    Image(systemName: proposal.origin == .agent ? "arrow.up" : "pencil")
                        .font(.headline).frame(width: 36, height: 36)
                }
                .buttonStyle(.borderedProminent).buttonBorderShape(.circle).tint(tint)
                .accessibilityLabel(proposal.origin == .agent ? "Send now" : "Edit")
                .accessibilityIdentifier("steer.proposalAction")
            }
            .padding(.horizontal, 14).padding(.vertical, 12)
            .background(
                GeometryReader { geometry in
                    ZStack(alignment: .leading) {
                        tint.opacity(0.12)
                        tint.opacity(0.28).frame(width: geometry.size.width * progress)
                    }
                }
            )
            .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
        }
        .accessibilityIdentifier("steer.proposal")
    }

    private var tint: Color { proposal.origin == .agent ? .purple : .blue }
}

/// "01:12 · from Ishara's number" while connected; the phase otherwise.
private struct CallTimerText: View {
    let connectedAt: Date?
    let phase: ActiveCallViewModel.Phase

    var body: some View {
        if let connectedAt, phase == .live {
            TimelineView(.periodic(from: connectedAt, by: 1)) { context in
                let seconds = Int(context.date.timeIntervalSince(connectedAt))
                Text(String(format: "%02d:%02d · from Ishara's number", seconds / 60, seconds % 60))
            }
        } else {
            Text("Calls come from Ishara's number")
        }
    }
}
