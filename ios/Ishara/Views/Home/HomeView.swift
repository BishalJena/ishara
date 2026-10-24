import CallSession
import SwiftUI

/// Screen 1: who to call, why, saved details and voice, then CALL.
struct HomeView: View {
    @State private var setup: CallSetup
    let modeDescription: String
    /// Why CALL can't work right now (for example no backend configured).
    let setupProblem: String?
    let onCall: (CallSetup) -> Void

    init(
        setup: CallSetup = .demo,
        modeDescription: String,
        setupProblem: String? = nil,
        onCall: @escaping (CallSetup) -> Void
    ) {
        _setup = State(initialValue: setup)
        self.modeDescription = modeDescription
        self.setupProblem = setupProblem
        self.onCall = onCall
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Who do you want to call?") {
                    Picker("Contact", selection: $setup.contact) {
                        ForEach(Contact.demoContacts) { contact in
                            Text(contact.name).tag(contact)
                        }
                    }
                    .pickerStyle(.inline)
                    .labelsHidden()

                    Label("New contact (coming later)", systemImage: "plus")
                        .foregroundStyle(.secondary)
                        .accessibilityLabel("New contact, not available in the demo")
                }

                Section("Purpose") {
                    Picker("Purpose", selection: $setup.purpose) {
                        ForEach(CallPurpose.allCases, id: \.self) { Text($0.title).tag($0) }
                    }
                }

                Section {
                    TextField("Your name", text: $setup.details.name)
                        .textContentType(.givenName)
                    Picker("Preferred time", selection: $setup.details.preferredTime) {
                        ForEach(PreferredTime.allCases) { Text($0.title).tag($0) }
                    }
                } header: {
                    Text("My details")
                } footer: {
                    Text("Used for quick replies and the drafted sentences.")
                }

                Section {
                    Picker("Voice", selection: $setup.voice) {
                        ForEach(CallVoice.allCases) { Text($0.title).tag($0) }
                    }
                }
            }
            .navigationTitle("Ishara")
            .safeAreaInset(edge: .bottom) {
                VStack(spacing: 10) {
                    if let setupProblem {
                        Label(setupProblem, systemImage: "exclamationmark.triangle.fill")
                            .font(.footnote)
                            .foregroundStyle(.red)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    Text(modeDescription)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    DisclosureNote()
                    Button {
                        onCall(setup)
                    } label: {
                        Label("CALL", systemImage: "phone.fill")
                    }
                    .buttonStyle(.bigAction(.green))
                    .disabled(setup.details.name.trimmingCharacters(in: .whitespaces).isEmpty || setupProblem != nil)
                    .accessibilityLabel("Call \(setup.contact.name)")
                    .accessibilityIdentifier("home.call")
                }
                .padding()
                .background(.bar)
            }
        }
    }
}

/// Path B calls come from Bolna's number; the user must know that before calling.
private struct DisclosureNote: View {
    var body: some View {
        Label {
            Text("Path B calls come from a Bolna number, not your own number.")
        } icon: {
            Image(systemName: "info.circle")
        }
        .font(.footnote)
        .foregroundStyle(.secondary)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

#Preview {
    HomeView(modeDescription: "Demo mode: a scripted call on this phone. Nothing is dialled.") { _ in }
}
