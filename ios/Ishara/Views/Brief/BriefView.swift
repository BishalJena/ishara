import CallSession
import SwiftUI

/// "Call for me" (decision D9): sign what you need, read the brief, approve it once.
struct BriefView: View {
    private static let briefCardID = "brief.card"

    @Bindable var model: BriefModel
    let modeDescription: String
    let onApprove: (CallSetup) -> Void
    let onBack: () -> Void

    var body: some View {
        NavigationStack {
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        signingSection
                        detailsSection
                        if let brief = model.brief {
                            BriefCard(brief: brief, contactName: model.setup.contact.name)
                                .id(Self.briefCardID)
                            Toggle(isOn: $model.attended) {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text("I'll stay and answer questions")
                                    Text(model.attended
                                         ? "The agent pauses and asks you here when a decision is yours."
                                         : "The agent says it will call back instead of deciding for you.")
                                        .font(.footnote)
                                        .foregroundStyle(.secondary)
                                }
                            }
                            .accessibilityIdentifier("brief.attended")
                        }
                        if let failure = model.failure {
                            Label(failure, systemImage: "exclamationmark.triangle.fill")
                                .foregroundStyle(.red)
                        }
                    }
                    .padding()
                }
                .onChange(of: model.brief != nil) { _, isShown in
                    guard isShown else { return }
                    withAnimation { proxy.scrollTo(Self.briefCardID, anchor: .top) }
                }
            }
            .navigationTitle("Call for me")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Back", action: onBack)
                }
            }
            .safeAreaInset(edge: .bottom) { bottomBar }
            .task { await model.run() }
        }
    }

    private var signingSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Sign what you need")
                .font(.headline)
            Text("For \(model.setup.purpose.title.lowercased()) at \(model.setup.contact.name). Sign the day and time, for example TOMORROW, MORNING.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            CameraCard(camera: model.recognition.camera, state: model.cameraState)
                .overlay(alignment: .bottomTrailing) {
                    ReplayMenu(recognition: model.recognition).padding(10)
                }
            if model.showsFramingHint {
                FramingHint()
            } else if model.lastSignUnsure {
                Label("That sign wasn't recognised. Sign it again, or tap it below.", systemImage: "questionmark.circle")
                    .font(.subheadline)
                    .foregroundStyle(.orange)
                    .accessibilityIdentifier("brief.unsure")
            }
            if let candidate = model.candidate {
                CandidateTile(sign: candidate, onAccept: model.acceptCandidate, onDismiss: model.dismissCandidate)
            }
            if !model.chips.isEmpty {
                FlowLayout(spacing: 8) {
                    ForEach(model.chips, id: \.self) { sign in
                        ChipView(chip: .recognised(sign)) { model.remove(sign) }
                    }
                }
            }
            let remaining = BriefModel.suggestions.filter { !model.chips.contains($0) }
            if !remaining.isEmpty {
                Text("Or tap:")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                FlowLayout(spacing: 8) {
                    ForEach(remaining, id: \.self) { sign in
                        Button(sign.rawValue) { model.add(sign) }
                            .buttonStyle(.bordered)
                            .accessibilityIdentifier("brief.add.\(sign.rawValue)")
                    }
                }
            }
        }
    }

    private var detailsSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("What the agent may share")
                .font(.headline)
            TextField("Your name", text: $model.name)
                .textContentType(.name)
                .textFieldStyle(.roundedBorder)
                .accessibilityIdentifier("brief.name")
            TextField("Callback number (optional)", text: $model.callback)
                .keyboardType(.phonePad)
                .textContentType(.telephoneNumber)
                .textFieldStyle(.roundedBorder)
                .accessibilityIdentifier("brief.callback")
            TextField("Reason, if they ask (optional)", text: $model.reason, axis: .vertical)
                .textFieldStyle(.roundedBorder)
                .accessibilityIdentifier("brief.reason")
            Text("Nothing else about you is ever said.")
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
    }

    private var bottomBar: some View {
        VStack(spacing: 10) {
            Text(modeDescription)
                .font(.footnote)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
            CallingNumberNote()
            if let approved = model.approvedSetup {
                Button {
                    onApprove(approved)
                } label: {
                    Label("Approve and call", systemImage: "phone.fill")
                }
                .buttonStyle(.bigAction(.green))
                .accessibilityHint("The agent calls \(model.setup.contact.name) and follows only this brief")
                .accessibilityIdentifier("brief.approve")
            } else {
                Button {
                    Task { await model.prepare() }
                } label: {
                    if model.isPreparing {
                        ProgressView()
                    } else {
                        Label("Prepare the request", systemImage: "doc.text.magnifyingglass")
                    }
                }
                .buttonStyle(.bigAction(.blue))
                .disabled(!model.canPrepare)
                .accessibilityIdentifier("brief.prepare")
            }
        }
        .padding()
        .background(.bar)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("brief.actionBar")
    }
}

/// The brief exactly as the agent will pursue it.
struct BriefCard: View {
    let brief: Brief
    let contactName: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("The agent follows only this brief with \(contactName)", systemImage: "checkmark.shield")
                .font(.headline)
            Text(brief.text)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("brief.text")
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.blue.opacity(0.1), in: RoundedRectangle(cornerRadius: 16))
    }
}
