import CallSession
import SwiftUI

/// Home for steer calls: who to call (a saved contact, or a typed or pasted number), what
/// the call is about, and the details Ishara may share. One tap places the call; Ishara
/// runs it and the user steps in whenever they like.
struct SetupView: View {
    let modeDescription: String
    /// Why a call can't be placed right now (for example no backend configured).
    let setupProblem: String?
    let history: CallHistory?
    let onCall: (CallSetup) -> Void

    @State private var contact: Contact = .cityClinic
    @State private var number = ""
    @State private var request = ""
    @State private var name = CallSetup.demo.details.name
    @State private var details: [Detail] = []
    @State private var newDetailLabel = ""
    @State private var newDetailValue = ""
    @FocusState private var focus: Field?

    private enum Field { case number, request, detailLabel, detailValue }

    private var typedContact: Contact? { Contact.number(number) }
    private var usesNumber: Bool { !number.trimmingCharacters(in: .whitespaces).isEmpty }

    private var problem: String? {
        if let setupProblem { return setupProblem }
        if usesNumber, typedContact == nil { return "Enter the number with its country code, like +91 98450 12345." }
        if request.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return "Say what the call is about." }
        if name.trimmingCharacters(in: .whitespaces).isEmpty { return "Add your name so Ishara can introduce you." }
        return nil
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    topBar
                    Text("Who are we\ncalling today?")
                        .font(.system(size: 36, weight: .bold))
                        .tracking(-0.8)
                        .accessibilityAddTraits(.isHeader)

                    composer

                    Text("Ishara leads the call from what you wrote and never adds anything else. It calls from Ishara's number, not yours. \(modeDescription)")
                        .font(.footnote)
                        .foregroundStyle(.secondary)

                    if let history, !history.records.isEmpty {
                        recent(history)
                    }
                }
                .padding(20)
            }
            .scrollDismissesKeyboard(.interactively)
            .toolbar(.hidden, for: .navigationBar)
        }
    }

    private var topBar: some View {
        HStack(spacing: 10) {
            Circle().fill(.yellow).frame(width: 36, height: 36)
                .overlay(Text(String(name.prefix(1)).uppercased()).font(.headline))
            Text("Hi \(name.split(separator: " ").first.map(String.init) ?? name)").font(.headline)
            Spacer()
            Image(systemName: "slider.horizontal.3")
                .frame(width: 36, height: 36)
                .background(Color(.secondarySystemBackground), in: Circle())
                .accessibilityLabel("Settings")
        }
    }

    private func recent(_ history: CallHistory) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Recent").font(.title3.weight(.bold))
            ForEach(history.records) { record in
                NavigationLink {
                    RecentCallView(history: history, id: record.id)
                } label: {
                    HStack(spacing: 12) {
                        Circle().fill(.purple).frame(width: 44, height: 44)
                            .overlay(Text(initials(record.contactName)).font(.subheadline.weight(.bold)).foregroundStyle(.white))
                        VStack(alignment: .leading, spacing: 3) {
                            Text(record.outcomeText).font(.subheadline.weight(.semibold)).foregroundStyle(.primary)
                            Text("\(record.contactName) · \(record.date.formatted(date: .abbreviated, time: .shortened))")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer()
                        Image(systemName: "chevron.right").imageScale(.small).foregroundStyle(.tertiary)
                    }
                    .padding(14)
                    .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 22, style: .continuous))
                }
                .buttonStyle(.plain)
            }
        }
    }

    private func initials(_ name: String) -> String {
        name.split(separator: " ").prefix(2).map { String($0.prefix(1)) }.joined().uppercased()
    }

    private var composer: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 10) {
                Text("To").font(.headline).foregroundStyle(.secondary)
                TextField("Number or contact", text: $number)
                    .keyboardType(.phonePad)
                    .textContentType(.telephoneNumber)
                    .focused($focus, equals: .number)
                    .accessibilityIdentifier("setup.number")
                if !usesNumber {
                    Menu {
                        ForEach(Contact.demoContacts) { saved in
                            Button(saved.name) { contact = saved }
                        }
                    } label: {
                        Label(contact.name, systemImage: "person.crop.circle")
                            .labelStyle(.titleAndIcon)
                            .font(.subheadline.weight(.semibold))
                    }
                    .accessibilityIdentifier("setup.contact")
                }
                if usesNumber {
                    Button("Clear", systemImage: "xmark.circle.fill") { number = "" }
                        .labelStyle(.iconOnly)
                        .foregroundStyle(.secondary)
                }
            }
            Divider()

            TextField("What should Ishara do? e.g. Book a check-up next week, mornings only.", text: $request, axis: .vertical)
                .lineLimit(3...6)
                .font(.title3.weight(.medium))
                .focused($focus, equals: .request)
                .accessibilityIdentifier("setup.request")

            HStack {
                Text("Your name").font(.subheadline).foregroundStyle(.secondary)
                TextField("Name", text: $name)
                    .textContentType(.name)
                    .accessibilityIdentifier("setup.name")
            }

            detailsSection

            if let problem {
                Label(problem, systemImage: "info.circle")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .accessibilityIdentifier("setup.problem")
            }
            HStack(alignment: .center, spacing: 8) {
                PasteButton(payloadType: String.self) { strings in
                    if let first = strings.first { number = first }
                }
                .labelStyle(.iconOnly)
                .buttonBorderShape(.circle)
                .tint(.primary)
                Button { focus = .number } label: {
                    Image(systemName: "person.crop.rectangle.stack").frame(width: 22, height: 22)
                }
                .buttonStyle(.bordered).buttonBorderShape(.circle).tint(.primary)
                .accessibilityLabel("Contacts")
                Spacer()
                Button(action: call) {
                    Label("Call", systemImage: "phone.fill")
                        .font(.headline)
                        .padding(.horizontal, 6)
                }
                .buttonStyle(.borderedProminent)
                .buttonBorderShape(.capsule)
                .tint(.green)
                .disabled(problem != nil)
                .accessibilityIdentifier("setup.call")
            }
        }
        .padding(16)
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 28, style: .continuous))
    }

    private var detailsSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Ishara may share")
                .font(.footnote.weight(.semibold))
                .foregroundStyle(.secondary)
            FlowLayout(spacing: 8) {
                ForEach(details, id: \.self) { detail in
                    Button {
                        details.removeAll { $0 == detail }
                    } label: {
                        Label("\(detail.label): \(detail.value)", systemImage: "xmark")
                            .labelStyle(.trailingIcon)
                            .font(.footnote.weight(.semibold))
                            .padding(.vertical, 6)
                            .padding(.horizontal, 10)
                            .background(Color.primary, in: Capsule())
                            .foregroundStyle(Color(.systemBackground))
                    }
                    .accessibilityLabel("Remove \(detail.label)")
                }
            }
            HStack(spacing: 8) {
                TextField("Detail, e.g. Date of birth", text: $newDetailLabel)
                    .focused($focus, equals: .detailLabel)
                TextField("Value", text: $newDetailValue)
                    .focused($focus, equals: .detailValue)
                    .onSubmit(addDetail)
                Button("Add", systemImage: "plus", action: addDetail)
                    .labelStyle(.iconOnly)
                    .disabled(newDetailLabel.trimmingCharacters(in: .whitespaces).isEmpty || newDetailValue.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            .font(.footnote)
            .textFieldStyle(.roundedBorder)
        }
    }

    private func addDetail() {
        let label = newDetailLabel.trimmingCharacters(in: .whitespaces)
        let value = newDetailValue.trimmingCharacters(in: .whitespaces)
        guard !label.isEmpty, !value.isEmpty, details.count < 12 else { return }
        details.append(Detail(label: label, value: value))
        newDetailLabel = ""
        newDetailValue = ""
        focus = nil
    }

    private func call() {
        guard problem == nil else { return }
        let who = typedContact ?? contact
        var setup = CallSetup.demo
        setup.contact = who
        setup.details.name = name.trimmingCharacters(in: .whitespaces)
        setup.request = request.trimmingCharacters(in: .whitespacesAndNewlines)
        setup.delegation = nil  // the brief is created next, with this request
        setup.voice = .indianEnglish
        onCall(setupWithDetails(setup))
    }

    private func setupWithDetails(_ setup: CallSetup) -> CallSetup {
        var setup = setup
        setup.sharedDetails = details
        return setup
    }
}

private struct TrailingIconLabelStyle: LabelStyle {
    func makeBody(configuration: Configuration) -> some View {
        HStack(spacing: 6) {
            configuration.title
            configuration.icon.imageScale(.small)
        }
    }
}

private extension LabelStyle where Self == TrailingIconLabelStyle {
    static var trailingIcon: TrailingIconLabelStyle { TrailingIconLabelStyle() }
}
