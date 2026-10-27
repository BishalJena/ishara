import CallSession
import Foundation

/// Someone the user can ask Ishara to call. The phone number lives only on the
/// backend allowlist; the app refers to a contact by its id.
struct Contact: Identifiable, Hashable, Sendable {
    let id: String
    let name: String
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
/// answer the agent's yes/no/wait questions (attended) or leave it to the agent (unattended).
struct Delegation: Equatable, Sendable {
    let brief: Brief
    let attended: Bool
}

/// Everything chosen on the Home screen before a call starts.
struct CallSetup: Equatable, Sendable {
    var contact: Contact
    var purpose: CallPurpose
    var details: SavedDetails
    var voice: CallVoice
    /// Set for a delegated call (D9); nil for a live call, where every sentence is approved.
    var delegation: Delegation? = nil

    /// The `POST /calls` body for this call. Starting a delegated call with its brief id is
    /// the user's one approval of that brief.
    var startRequest: StartCallRequest {
        guard let delegation else { return StartCallRequest(contactID: contact.id, purpose: purpose) }
        return StartCallRequest(
            contactID: contact.id, purpose: purpose, mode: .delegated,
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
