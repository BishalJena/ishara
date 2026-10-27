import CallSession
import SwiftUI

/// Screen 1: who to call, why, saved details and voice, then CALL.
struct HomeView: View {
    @State private var setup: CallSetup
    let modeDescription: String
    /// Why CALL can't work right now (for example no backend configured).
    let setupProblem: String?
    let onCall: (CallSetup) -> Void
    /// D9: the agent makes the call from a brief the user signs and approves.
    let onCallForMe: ((CallSetup) -> Void)?

    init(
        setup: CallSetup = .demo,
        modeDescription: String,
        setupProblem: String? = nil,
        onCall: @escaping (CallSetup) -> Void,
        onCallForMe: ((CallSetup) -> Void)? = nil
    ) {
        _setup = State(initialValue: setup)
        self.modeDescription = modeDescription
        self.setupProblem = setupProblem
        self.onCall = onCall
        self.onCallForMe = onCallForMe
    }

    private var canCall: Bool {
        !setup.details.name.trimmingCharacters(in: .whitespaces).isEmpty && setupProblem == nil
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
                    CallingNumberNote()
                    Button {
                        onCall(setup)
                    } label: {
                        Label("CALL", systemImage: "phone.fill")
                    }
                    .buttonStyle(.bigAction(.green))
                    .disabled(!canCall)
                    .accessibilityLabel("Call \(setup.contact.name)")
                    .accessibilityHint("You sign each reply and approve it with SEND")
                    .accessibilityIdentifier("home.call")
                    if let onCallForMe {
                        Button {
                            onCallForMe(setup)
                        } label: {
                            Label("CALL FOR ME", systemImage: "person.wave.2.fill")
                        }
                        .buttonStyle(.bigAction(.blue))
                        .disabled(!canCall)
                        .accessibilityLabel("Let the agent call \(setup.contact.name) for you")
                        .accessibilityHint("Sign what you need, approve the brief once, and read the notes after")
                        .accessibilityIdentifier("home.callForMe")
                    }
                }
                .padding()
                .background(.bar)
            }
        }
    }
}

/// Calls come from Ishara's calling number (Bolna's, Path B), never the user's own, and
/// the receptionist hears an automated voice. Shown on Home and again on Get ready, right
/// before the call is placed, so the user knows both before calling.
struct CallingNumberNote: View {
    var body: some View {
        Label {
            Text("Calls are placed from Ishara's calling number, not your own number. The receptionist hears an automated voice reading what you approve.")
        } icon: {
            Image(systemName: "info.circle")
        }
        .font(.footnote)
        .foregroundStyle(.secondary)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("callingNumberNote")
    }
}

#Preview {
    HomeView(modeDescription: "Demo mode: a scripted call on this phone. Nothing is dialled.") { _ in }
}
