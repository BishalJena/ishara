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
    @State private var activity = CallActivityController()
    @State private var typed = ""
    /// What the user last sent, shown under its polished preview.
    @State private var lastTyped = ""
    @State private var isSigning = false
    @FocusState private var typing: Bool

    var body: some View {
        VStack(spacing: 0) {
            header
            statusPill
            factsStrip
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
        .onChange(of: model.isCallOver) { _, isOver in
            if isOver {
                typing = false
                activity.end(outcome: "Call ended · open Ishara for the gist")
            }
        }
        .onAppear { activity.start(contactName: model.setup.contact.name) }
        .onDisappear { activity.end(outcome: nil) }
        .onChange(of: model.captions.count) { _, _ in activity.update(from: model) }
        .onChange(of: model.phase) { _, _ in activity.update(from: model) }
        .onChange(of: model.isSteppingIn) { _, _ in activity.update(from: model) }
        .onReceive(NotificationCenter.default.publisher(for: .isharaEndCallRequested)) { _ in model.end() }
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

    // MARK: Facts strip

    /// Times, days and amounts the receptionist said, pinned so they needn't be reread.
    private var factsStrip: some View {
        let facts = CallFacts.extract(from: model.captions.filter { $0.speaker == .receptionist }.map(\.text))
        return Group {
            if !facts.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        ForEach(facts, id: \.self) { fact in
                            Label(fact.text, systemImage: fact.symbol)
                                .font(.caption.weight(.bold))
                                .padding(.vertical, 5).padding(.horizontal, 9)
                                .background(Color.yellow.opacity(0.22), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                                .foregroundStyle(Color(red: 0.6, green: 0.42, blue: 0))
                        }
                    }
                    .padding(.horizontal, 20).padding(.top, 8)
                }
                .accessibilityIdentifier("steer.facts")
            }
        }
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

    /// Why the call didn't get through, if it didn't: it never started, or ended with no
    /// receptionist line heard.
    private var notThrough: String? {
        if let failure = model.startFailure { return failure }
        guard case .ended(let reason) = model.phase else { return nil }
        if case .failed(let text) = reason { return text }
        if reason == .remoteEnded, !model.captions.contains(where: { $0.speaker == .receptionist }) {
            return "\(model.setup.contact.name) didn't answer."
        }
        return nil
    }

    @ViewBuilder
    private var composer: some View {
        if let problem = notThrough {
            NotThroughTray(problem: problem, onCallAgain: onLeave, onShowNotes: onShowNotes)
        } else {
            replyPanel
        }
    }

    private var replyPanel: some View {
        VStack(spacing: 10) {
            if model.isSteppingIn, !isSigning, let cover = model.captions.last(where: { $0.speaker == .agent }) {
                CoverLine(text: cover.text, since: cover.at)
            }
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
                if proposal.origin == .user, !lastTyped.isEmpty {
                    Text("You typed: “\(lastTyped)”")
                        .font(.caption2).foregroundStyle(.secondary)
                        .accessibilityIdentifier("steer.youTyped")
                }
            }
            if isSigning {
                signingPanel
            } else if !model.isCallOver {
                if model.proposal == nil, !typing, case .live = model.phase {
                    quickReplies
                }
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

    /// One-tap replies drawn from what the receptionist just asked; each goes out like a
    /// typed line (polished, previewed, spoken).
    private var quickReplies: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(QuickSteerReply.suggestions(for: model.captions.last(where: { $0.speaker == .receptionist })?.text), id: \.self) { reply in
                    Button(reply) {
                        model.beginSteppingIn()
                        lastTyped = reply
                        model.say(reply)
                    }
                    .buttonStyle(.bordered).buttonBorderShape(.capsule).controlSize(.small)
                    .font(.footnote.weight(.semibold))
                }
            }
            .padding(.horizontal, 4)
        }
        .accessibilityIdentifier("steer.quickReplies")
    }

    private func sendTyped() {
        let text = typed.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        lastTyped = text
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
                .accessibilityElement(children: .ignore)
                .accessibilityAddTraits(.isButton)
                .accessibilityLabel(proposal.origin == .agent ? "Ishara will say \(proposal.text). Tap to edit." : "Saying \(proposal.text). Tap to edit.")
                .accessibilityIdentifier("steer.proposal")
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
    }

    private var tint: Color { proposal.origin == .agent ? .purple : .blue }
}

/// The call didn't get through: nothing was said, so nothing to undo. Offers the ways back.
private struct NotThroughTray: View {
    let problem: String
    let onCallAgain: () -> Void
    let onShowNotes: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Label("Didn't get through", systemImage: "phone.arrow.down.left")
                .font(.headline).foregroundStyle(.red)
            Text(problem).font(.title3.weight(.bold))
            Text("Nothing was said on your behalf. Your request is kept, so you can try again when it suits you.")
                .font(.footnote).foregroundStyle(.secondary)
            HStack(spacing: 8) {
                Button("Back to the request", systemImage: "arrow.uturn.left", action: onCallAgain)
                    .buttonStyle(.bordered).buttonBorderShape(.capsule)
                Button("What happened", systemImage: "list.bullet.rectangle", action: onShowNotes)
                    .buttonStyle(.borderedProminent).buttonBorderShape(.capsule)
            }
            .controlSize(.large)
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 28, style: .continuous))
        .padding(10)
        .accessibilityIdentifier("steer.notThrough")
    }
}

/// While the user types: what Ishara just said to the receptionist to cover the pause, and
/// how long they've been waiting.
private struct CoverLine: View {
    let text: String
    let since: Date

    var body: some View {
        TimelineView(.periodic(from: since, by: 1)) { context in
            HStack(spacing: 8) {
                Image(systemName: "waveform").foregroundStyle(.purple)
                VStack(alignment: .leading, spacing: 1) {
                    Text("Ishara just said").font(.caption2.weight(.semibold)).foregroundStyle(.purple)
                    Text("“\(text)”").font(.footnote.weight(.semibold))
                }
                Spacer()
                Text("\(Int(context.date.timeIntervalSince(since))) s")
                    .font(.caption.weight(.bold)).foregroundStyle(.secondary)
                    .accessibilityLabel("waiting \(Int(context.date.timeIntervalSince(since))) seconds")
            }
            .padding(.horizontal, 14).padding(.vertical, 10)
            .background(Color.purple.opacity(0.08), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        }
        .accessibilityIdentifier("steer.cover")
    }
}

/// Days, clock times and amounts in the receptionist's words, as pinned facts.
enum CallFacts {
    struct Fact: Hashable {
        let text: String
        let symbol: String
    }

    private static let patterns: [(String, String)] = [
        (#"\b\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)\b"#, "clock"),
        (#"\b\d{1,2}:\d{2}\b"#, "clock"),
        (#"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|tomorrow|today)\b(?:\s+(?:morning|afternoon|evening))?"#, "calendar"),
        (#"(?:₹|Rs\.?\s?)\d[\d,]*"#, "indianrupeesign.circle"),
    ]

    static func extract(from lines: [String]) -> [Fact] {
        var seen: [Fact] = []
        for line in lines {
            for (pattern, symbol) in patterns {
                guard let regex = try? NSRegularExpression(pattern: pattern, options: .caseInsensitive) else { continue }
                for match in regex.matches(in: line, range: NSRange(line.startIndex..., in: line)) {
                    guard let range = Range(match.range, in: line) else { continue }
                    let fact = Fact(text: String(line[range]), symbol: symbol)
                    if !seen.contains(fact) { seen.append(fact) }
                }
            }
        }
        return Array(seen.suffix(6))
    }
}

/// One-tap replies for the receptionist's last line: a time on offer gets yes/no; a question
/// gets a repeat; everything gets "hold on".
enum QuickSteerReply {
    static func suggestions(for lastLine: String?) -> [String] {
        let line = (lastLine ?? "").lowercased()
        var replies: [String] = []
        let times = CallFacts.extract(from: [lastLine ?? ""]).filter { $0.symbol != "indianrupeesign.circle" }
        if let time = times.last {
            replies += ["Yes, \(time.text) works", "\(time.text) doesn't work, anything else?"]
        } else if line.contains("?") {
            replies += ["Yes", "No"]
        }
        replies += ["Could you repeat that?", "One moment, please"]
        return replies
    }
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
