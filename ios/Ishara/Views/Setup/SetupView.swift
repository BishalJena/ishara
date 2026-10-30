import CallSession
import PhotosUI
import SwiftUI

/// Home for steer calls: who to call (a typed or pasted number, a contact, or someone called
/// before), what the call is about, and the details Ishara may share, typed or read from an
/// attached photo or PDF on this phone. One tap places the call; Ishara
/// runs it and the user steps in whenever they like.
struct SetupView: View {
    let modeDescription: String
    /// Why a call can't be placed right now (for example no backend configured).
    let setupProblem: String?
    let history: CallHistory?
    let onCall: (CallSetup) -> Void

    @State private var number = ""
    @State private var pickedName = ""
    @State private var request = ""
    @AppStorage("ishara.name") private var name = ""
    @AppStorage("ishara.callback") private var callback = ""
    @State private var showsSettings = false
    @State private var callAfterSettings = false
    @State private var showsContacts = false
    @State private var showsPhotoPicker = false
    @State private var showsFilePicker = false
    @State private var showsAttachMenu = false
    @State private var photoItem: PhotosPickerItem?
    @State private var attachments: [Attachment] = []
    @State private var reading = 0
    /// Details the user tapped to keep private, by label.
    @State private var privateLabels: Set<String> = []
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @FocusState private var focus: Field?

    private enum Field { case number, request }

    private var typedContact: Contact? { Contact.indian(number, name: pickedName) }
    private var usesNumber: Bool { !number.isEmpty }

    /// What Ishara noticed in the request (and in anything attached, which is written into
    /// the request too), so there's one place the user reads and edits.
    private var inferred: [Detail] { DetailExtractor.extract(from: request) }
    private var shared: [Detail] { inferred.filter { !privateLabels.contains($0.label) } }

    /// People called before from this phone, newest first, one chip each.
    private var recentPeople: [Contact] {
        var seen = Set<String>()
        return (history?.records ?? []).compactMap { record -> Contact? in
            guard let number = record.contactNumber, seen.insert(number).inserted else { return nil }
            return Contact.number(number, name: record.contactName == number ? nil : record.contactName)
        }
    }

    private var problem: String? {
        if let setupProblem { return setupProblem }
        if !usesNumber { return "Enter a number, or pick someone." }
        if typedContact == nil { return "Enter the 10-digit number." }
        if request.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return "Say what the call is about." }
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
            .onAppear {
                // UI tests start with a clean store and no way to type into Settings first.
                if name.isEmpty, let preset = ProcessInfo.processInfo.environment["ISHARA_UITEST_NAME"] { name = preset }
            }
            .sheet(isPresented: $showsSettings, onDismiss: {
                guard callAfterSettings else { return }
                callAfterSettings = false
                if !name.trimmingCharacters(in: .whitespaces).isEmpty { call() }
            }) { SettingsSheet(reason: callAfterSettings ? "Ishara introduces you by name on the call. Add it once; it stays on this phone." : nil) }
            .sheet(isPresented: $showsContacts) {
                ContactPicker { pickedName, pickedNumber in
                    self.pickedName = pickedName
                    number = Contact.indianDigits(from: pickedNumber)
                }
                .ignoresSafeArea()
            }
            .confirmationDialog("Attach", isPresented: $showsAttachMenu) {
                Button("Photo") { showsPhotoPicker = true }
                Button("File or PDF") { showsFilePicker = true }
            } message: {
                Text("Read on this iPhone. Only the details you keep are shared on the call.")
            }
            .photosPicker(isPresented: $showsPhotoPicker, selection: $photoItem, matching: .images)
            .onChange(of: photoItem) { _, item in
                guard let item else { return }
                photoItem = nil
                Task {
                    if let data = try? await item.loadTransferable(type: Data.self) { await attach(data, name: "Photo") }
                }
            }
            .fileImporter(isPresented: $showsFilePicker, allowedContentTypes: [.pdf, .image]) { result in
                guard case let .success(url) = result else { return }
                Task {
                    let accessed = url.startAccessingSecurityScopedResource()
                    defer { if accessed { url.stopAccessingSecurityScopedResource() } }
                    if let data = try? Data(contentsOf: url) { await attach(data, name: url.lastPathComponent) }
                }
            }
        }
    }

    private func attach(_ data: Data, name: String) async {
        reading += 1
        let attachment = await AttachmentReader.read(data: data, name: name)
        reading -= 1
        withAnimation(motion) {
            attachments.append(attachment)
            if !attachment.sentence.isEmpty {
                request = request.trimmingCharacters(in: .whitespacesAndNewlines) + (request.isEmpty ? "" : "\n") + attachment.sentence
            }
        }
    }

    private func remove(_ attachment: Attachment) {
        withAnimation(motion) {
            attachments.removeAll { $0.id == attachment.id }
            request = request.replacingOccurrences(of: attachment.sentence, with: "").trimmingCharacters(in: .whitespacesAndNewlines)
        }
    }

    /// A settled spring (no bounce) for things that appear because of what the user did;
    /// a plain fade with Reduce Motion on.
    private var motion: Animation { reduceMotion ? .easeOut(duration: 0.2) : .spring(duration: 0.4, bounce: 0) }
    private var appear: AnyTransition {
        reduceMotion ? .opacity : .scale(scale: 0.85, anchor: .leading).combined(with: .opacity)
    }

    private var topBar: some View {
        HStack(spacing: 10) {
            Circle().fill(.yellow).frame(width: 36, height: 36)
                .overlay(Text(String(name.prefix(1)).uppercased()).font(.headline))
            Text(name.isEmpty ? "Hi there" : "Hi \(name.split(separator: " ").first.map(String.init) ?? name)").font(.headline)
            Spacer()
            Button { showsSettings = true } label: {
                Image(systemName: "slider.horizontal.3")
                    .frame(width: 36, height: 36)
                    .background(Color(.secondarySystemBackground), in: Circle())
            }
            .tint(.primary)
            .accessibilityLabel("Settings")
            .accessibilityIdentifier("setup.settings")
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
                Text("+91").font(.body.monospacedDigit()).foregroundStyle(usesNumber ? .primary : .secondary)
                    .accessibilityHidden(true)
                TextField("10-digit number", text: $number)
                    .keyboardType(.numberPad)
                    .textContentType(.telephoneNumber)
                    .font(.body.monospacedDigit())
                    .focused($focus, equals: .number)
                    .onChange(of: number) { _, raw in
                        let digits = raw.count > 10 ? Contact.indianDigits(from: raw) : raw.filter(\.isNumber)
                        if digits != raw { number = digits }
                    }
                    .accessibilityLabel("Number, +91")
                    .accessibilityIdentifier("setup.number")
                if usesNumber {
                    if !pickedName.isEmpty { Text(pickedName).font(.subheadline.weight(.semibold)).lineLimit(1) }
                    Button("Clear", systemImage: "xmark.circle.fill") { number = ""; pickedName = "" }
                        .labelStyle(.iconOnly)
                        .foregroundStyle(.secondary)
                }
            }
            if !usesNumber, !recentPeople.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(recentPeople) { person in
                            Button {
                                number = Contact.indianDigits(from: person.phoneNumber ?? "")
                                pickedName = person.name == person.phoneNumber ? "" : person.name
                            } label: {
                                Label(person.name, systemImage: "clock.arrow.circlepath")
                                    .font(.footnote.weight(.semibold))
                                    .padding(.vertical, 6).padding(.horizontal, 10)
                                    .background(Color(.tertiarySystemBackground), in: Capsule())
                            }
                            .tint(.primary)
                        }
                    }
                }
                .accessibilityIdentifier("setup.recentPeople")
            }
            Divider()

            TextField("What should Ishara do? e.g. Book a check-up next week, mornings only. My policy number is …", text: $request, axis: .vertical)
                .lineLimit(3...8)
                .font(.title3.weight(.medium))
                .focused($focus, equals: .request)
                .accessibilityIdentifier("setup.request")

            if !attachments.isEmpty || reading > 0 { attachmentsRow }

            if !inferred.isEmpty { noticedSection }
            // The section itself slides in with the first detail and out with the last.
            Color.clear.frame(height: 0).animation(motion, value: inferred.isEmpty)

            if let problem {
                Label(problem, systemImage: "info.circle")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .accessibilityIdentifier("setup.problem")
            }
            HStack(alignment: .center, spacing: 8) {
                Button { showsAttachMenu = true } label: {
                    Image(systemName: "paperclip").frame(width: 22, height: 22)
                }
                .buttonStyle(.bordered).buttonBorderShape(.circle).tint(.primary)
                .accessibilityLabel("Attach a photo or file")
                .accessibilityIdentifier("setup.attach")
                Button { showsContacts = true } label: {
                    Image(systemName: "person.crop.circle").frame(width: 22, height: 22)
                }
                .buttonStyle(.bordered).buttonBorderShape(.circle).tint(.primary)
                .accessibilityLabel("Contacts")
                .accessibilityIdentifier("setup.contacts")
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

    private var attachmentsRow: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(attachments) { attachment in
                HStack(spacing: 10) {
                    if let thumbnail = attachment.thumbnail {
                        Image(uiImage: thumbnail).resizable().scaledToFill()
                            .frame(width: 36, height: 36).clipShape(RoundedRectangle(cornerRadius: 8))
                    } else {
                        Image(systemName: "doc").frame(width: 36, height: 36)
                    }
                    VStack(alignment: .leading, spacing: 1) {
                        Text(attachment.name).font(.subheadline.weight(.semibold)).lineLimit(1)
                        Text(attachment.problem ?? "Read on this iPhone · \(attachment.details.count) detail\(attachment.details.count == 1 ? "" : "s") found")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button("Remove", systemImage: "xmark.circle.fill") { remove(attachment) }
                        .labelStyle(.iconOnly).foregroundStyle(.secondary)
                }
                .transition(appear)
            }
            if reading > 0 {
                Label("Reading on this iPhone…", systemImage: "doc.text.magnifyingglass")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    /// The details Ishara noticed in the request, as chips that spring in as they're typed.
    /// Tap one to keep it private (it stays in the text; Ishara just won't say it).
    private var noticedSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Ishara may share", systemImage: "sparkles")
                .font(.footnote.weight(.semibold))
                .foregroundStyle(.secondary)
            FlowLayout(spacing: 8) {
                ForEach(inferred, id: \.label) { detail in
                    let isPrivate = privateLabels.contains(detail.label)
                    Button {
                        withAnimation(motion) {
                            if isPrivate { privateLabels.remove(detail.label) } else { privateLabels.insert(detail.label) }
                        }
                    } label: {
                        HStack(spacing: 4) {
                            Text(detail.label).foregroundStyle(isPrivate ? .secondary : Color(.systemBackground).opacity(0.7))
                            Text(detail.value).strikethrough(isPrivate)
                            if isPrivate { Image(systemName: "eye.slash").imageScale(.small) }
                        }
                        .font(.footnote.weight(.semibold))
                        .padding(.vertical, 6)
                        .padding(.horizontal, 10)
                        .background(isPrivate ? Color(.tertiarySystemBackground) : Color.primary, in: Capsule())
                        .foregroundStyle(isPrivate ? Color.secondary : Color(.systemBackground))
                    }
                    .accessibilityLabel("\(detail.label), \(detail.value)\(isPrivate ? ", kept private" : "")")
                    .accessibilityHint(isPrivate ? "Double-tap to let Ishara share it" : "Double-tap to keep it private")
                    .transition(appear)
                }
            }
            Text("Tap a detail to keep it private.")
                .font(.caption2).foregroundStyle(.tertiary)
        }
        .animation(motion, value: inferred.map(\.label))
        .sensoryFeedback(.selection, trigger: inferred.count)
        .transition(appear)
    }

    private func call() {
        guard problem == nil, let who = typedContact else { return }
        if name.trimmingCharacters(in: .whitespaces).isEmpty {
            callAfterSettings = true
            showsSettings = true
            return
        }
        var setup = CallSetup(
            contact: who, purpose: .doctorAppointment,
            details: SavedDetails(name: name.trimmingCharacters(in: .whitespaces), preferredTime: .mornings),
            voice: .indianEnglish)
        setup.request = request.trimmingCharacters(in: .whitespacesAndNewlines)
        setup.sharedDetails = shared
        if callback.count == 10, !shared.contains(where: { $0.label == "Phone" }) {
            setup.sharedDetails.append(Detail(label: "Callback number", value: "+91 " + callback))
        }
        onCall(setup)
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
