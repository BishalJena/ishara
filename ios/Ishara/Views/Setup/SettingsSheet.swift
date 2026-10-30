import SwiftUI

/// What Ishara says about you on every call, kept on this phone.
struct SettingsSheet: View {
    /// Set when the sheet opens because a call needs the name: it says why, focuses the
    /// field, and its Call button continues the call (Cancel doesn't).
    var onContinueCall: (() -> Void)? = nil
    private var forCall: Bool { onContinueCall != nil }
    @AppStorage("ishara.name") private var name = ""
    @AppStorage("ishara.callback") private var callback = ""
    @Environment(\.dismiss) private var dismiss
    @FocusState private var nameFocused: Bool

    private var hasName: Bool { !name.trimmingCharacters(in: .whitespaces).isEmpty }

    var body: some View {
        NavigationStack {
            Form {
                if forCall {
                    Section {
                        Label("Ishara introduces you by name on the call. Add it once; it stays on this phone.",
                              systemImage: "person.wave.2")
                            .font(.subheadline)
                    }
                    .accessibilityIdentifier("settings.reason")
                }
                Section {
                    TextField("Your name", text: $name)
                        .textContentType(.name)
                        .submitLabel(.done)
                        .focused($nameFocused)
                        .onSubmit { if forCall, hasName { continueCall() } }
                        .accessibilityIdentifier("settings.name")
                    HStack(spacing: 6) {
                        Text("+91").foregroundStyle(.secondary)
                        TextField("Callback number (optional)", text: $callback)
                            .keyboardType(.numberPad)
                            .onChange(of: callback) { _, raw in
                                let digits = raw.count > 10 ? Contact.indianDigits(from: raw) : raw.filter(\.isNumber)
                                if digits != raw { callback = digits }
                            }
                            .accessibilityIdentifier("settings.callback")
                    }
                } header: {
                    Text("About you")
                } footer: {
                    Text("Ishara gives the callback number only if they ask how to reach you. Every call opens by saying Ishara is calling for a Deaf caller, from Ishara's number, not yours.")
                }
            }
            .navigationTitle(forCall ? "Before the call" : "Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button(forCall ? "Call" : "Done") { forCall ? continueCall() : dismiss() }
                        .disabled(forCall && !hasName)
                        .accessibilityIdentifier("settings.done")
                }
                if forCall {
                    ToolbarItem(placement: .cancellationAction) {
                        Button("Cancel") { dismiss() }
                    }
                }
            }
            .onAppear { if forCall { nameFocused = true } }
        }
    }

    private func continueCall() {
        name = name.trimmingCharacters(in: .whitespaces)
        onContinueCall?()
        dismiss()
    }
}
