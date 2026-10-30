import CallSession
import Foundation

/// Someone the user can ask Ishara to call. The phone number lives only on the
/// backend allowlist; the app refers to a contact by its id.
struct Contact: Identifiable, Hashable, Sendable {
    let id: String
    let name: String
    /// A number the user typed or pasted (E.164). The backend dials it only when it is on
    /// its allowlist; saved contacts have none and are dialled by id.
    var phoneNumber: String? = nil

    /// A typed or pasted number as a contact; the name defaults to the number, spaced.
    static func number(_ digits: String, name: String? = nil) -> Contact? {
        let e164 = digits.filter { $0.isNumber || $0 == "+" }
        guard e164.range(of: #"^\+[1-9]\d{6,14}$"#, options: .regularExpression) != nil else { return nil }
        let given = name.map { $0.trimmingCharacters(in: .whitespaces) } ?? ""
        return Contact(id: "number", name: given.isEmpty || isNumberName(given) ? display(e164) : given, phoneNumber: e164)
    }

    /// "+919337473802" as people write it: "+91 93374 73802".
    static func display(_ e164: String) -> String {
        let digits = e164.filter(\.isNumber)
        guard e164.hasPrefix("+91"), digits.count == 12 else { return e164 }
        let national = digits.dropFirst(2)
        return "+91 \(national.prefix(5)) \(national.suffix(5))"
    }

    /// A "name" that is really a number (a record of a call to a typed number).
    static func isNumberName(_ name: String) -> Bool {
        guard let first = name.first else { return false }
        return first == "+" || first.isNumber
    }

    /// An Indian number from its 10 national digits (the app is India-only, so +91 is implied).
    static func indian(_ digits: String, name: String? = nil) -> Contact? {
        let digits = digits.filter(\.isNumber)
        guard digits.count == 10, let first = digits.first, first != "0", first != "1" else { return nil }
        return number("+91" + digits, name: name)
    }

    /// The 10 national digits of a number typed or picked in any common Indian form:
    /// "+91 98450 12345", "098450 12345", "9845012345".
    static func indianDigits(from raw: String) -> String {
        var digits = raw.filter(\.isNumber)
        if digits.count == 12, digits.hasPrefix("91") { digits.removeFirst(2) }
        if digits.count == 11, digits.hasPrefix("0") { digits.removeFirst() }
        return String(digits.prefix(10))
    }
}

extension CallPurpose {
    var title: String {
        switch self {
        case .doctorAppointment: "Doctor's appointment"
        }
    }
}

enum PreferredTime: String, CaseIterable, Identifiable, Sendable {
    case mornings, afternoons, evenings

    var id: String { rawValue }
    var title: String { rawValue.capitalized }
}

enum CallVoice: String, CaseIterable, Identifiable, Sendable {
    case indianEnglish = "en-IN"

    var id: String { rawValue }

    var title: String {
        switch self {
        case .indianEnglish: "Indian English"
        }
    }
}

/// Details the user saved once so quick replies and the composer can use them.
struct SavedDetails: Equatable, Sendable {
    var name: String
    var preferredTime: PreferredTime
}

/// Decision D9: the brief the user read and approved, and whether they stay on the call to
/// answer the agent's questions (attended) or leave it to the agent (unattended).
struct Delegation: Equatable, Sendable {
    let brief: Brief
    let attended: Bool
    /// `.delegated` (D9) or `.steer`: the agent runs the call and the user may step in.
    var mode: CallMode = .delegated
}

/// Everything chosen on the Home screen before a call starts.
struct CallSetup: Equatable, Sendable {
    var contact: Contact
    var purpose: CallPurpose
    var details: SavedDetails
    var voice: CallVoice
    /// Set for a delegated or steer call; nil for a live call, where every sentence is approved.
    var delegation: Delegation? = nil
    /// Steer call: what the user typed the call is about.
    var request: String? = nil
    /// Steer call: facts the user approved for sharing when the receptionist asks.
    var sharedDetails: [Detail] = []
    /// Cards, letters or bills the user attached, as text read on the phone.
    var documents: [Document] = []
    /// The user's callback number from Settings, given only if they ask how to reach them.
    var callback: String? = nil

    var isSteer: Bool { delegation?.mode == .steer }

    /// The brief request for a steer call: the typed request plus the profile and details.
    var steerBriefRequest: BriefRequest {
        BriefRequest(
            purpose: purpose, chips: [],
            profile: Profile(name: details.name, callback: callback, details: sharedDetails, documents: documents),
            request: request)
    }

    /// The `POST /calls` body for this call. Starting a delegated call with its brief id is
    /// the user's one approval of that brief.
    var startRequest: StartCallRequest {
        let contactID = contact.phoneNumber == nil ? contact.id : nil
        guard let delegation else {
            return StartCallRequest(contactID: contactID, phoneNumber: contact.phoneNumber, purpose: purpose)
        }
        return StartCallRequest(
            contactID: contactID, phoneNumber: contact.phoneNumber, purpose: purpose, mode: delegation.mode,
            briefID: delegation.brief.briefID, attended: delegation.attended)
    }
}

extension Contact {
    static let cityClinic = Contact(id: "clinic", name: "City Clinic")
    static let mehtaOffice = Contact(id: "mehta-office", name: "Dr. Mehta's office")

    /// Synthetic demo contacts. Real numbers stay in the backend allowlist.
    static let demoContacts: [Contact] = [.cityClinic, .mehtaOffice]
}

extension CallSetup {
    /// Synthetic details for the rehearsed clinic call (PLAN §1).
    static let demo = CallSetup(
        contact: .cityClinic,
        purpose: .doctorAppointment,
        details: SavedDetails(name: "Riya", preferredTime: .mornings),
        voice: .indianEnglish
    )
}
