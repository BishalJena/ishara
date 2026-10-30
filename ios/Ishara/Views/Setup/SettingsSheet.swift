import SwiftUI

/// What Ishara says about you on every call, kept on this phone.
struct SettingsSheet: View {
    /// Shown at the top when the sheet opens because a call needs something, e.g. the name.
    var reason: String? = nil
    @AppStorage("ishara.name") private var name = ""
    @AppStorage("ishara.callback") private var callback = ""
    @AppStorage("ishara.sayDeaf") private var sayDeaf = true
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Your name", text: $name).textContentType(.name)
                        .accessibilityIdentifier("settings.name")
                    HStack(spacing: 6) {
                        Text("+91").foregroundStyle(.secondary)
                        TextField("Callback number (optional)", text: $callback)
                            .keyboardType(.numberPad)
                            .onChange(of: callback) { _, raw in
                                let digits = raw.count > 10 ? Contact.indianDigits(from: raw) : raw.filter(\.isNumber)
                                if digits != raw { callback = digits }
                            }
                    }
                } header: {
                    Text("About you")
                } footer: {
                    if let reason { Text(reason) }
                }
                Section {
                    Toggle("Say I'm Deaf and using Ishara", isOn: $sayDeaf)
                } footer: {
                    Text("Ishara opens every call by saying it's calling for a Deaf caller, so the other side expects short pauses. It calls from Ishara's number, not yours.")
                }
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
    }
}
