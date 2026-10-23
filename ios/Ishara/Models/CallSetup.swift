import Foundation

/// Someone the user can ask Ishara to call. The phone number lives only on the
/// backend allowlist; the app refers to a contact by its id.
struct Contact: Identifiable, Hashable, Sendable {
    let id: String
    let name: String
}

enum CallPurpose: String, CaseIterable, Identifiable, Sendable {
    case doctorsAppointment = "doctors_appointment"

    var id: String { rawValue }

    var title: String {
        switch self {
        case .doctorsAppointment: "Doctor's appointment"
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

/// Everything chosen on the Home screen before a call starts.
struct CallSetup: Equatable, Sendable {
    var contact: Contact
    var purpose: CallPurpose
    var details: SavedDetails
    var voice: CallVoice
}

extension Contact {
    static let cityClinic = Contact(id: "city-clinic", name: "City Clinic")
    static let mehtaOffice = Contact(id: "mehta-office", name: "Dr. Mehta's office")

    /// Synthetic demo contacts. Real numbers stay in the backend allowlist.
    static let demoContacts: [Contact] = [.cityClinic, .mehtaOffice]
}

extension CallSetup {
    /// Synthetic details for the rehearsed clinic call (PLAN §1).
    static let demo = CallSetup(
        contact: .cityClinic,
        purpose: .doctorsAppointment,
        details: SavedDetails(name: "Riya", preferredTime: .mornings),
        voice: .indianEnglish
    )
}
