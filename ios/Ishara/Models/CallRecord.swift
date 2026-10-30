import CallSession
import Foundation

/// One finished call as kept on this phone (Recent calls): only what the call and notes
/// screens showed. No phone numbers: the app never has the contact's, and the user's
/// callback number stays in the brief request, which is not kept.
struct CallRecord: Codable, Equatable, Identifiable, Sendable {
    /// A caption from the call screen. `CaptionSpeaker` has no user, so it isn't reused.
    struct Line: Codable, Equatable, Sendable {
        enum Speaker: String, Codable, Sendable {
            case receptionist, agent, user
        }

        var speaker: Speaker
        var text: String
        var at: Date
    }

    let id: UUID
    let date: Date
    let contactName: String
    /// The number dialled, when the user typed or picked one, so Home can offer it again.
    var contactNumber: String? = nil
    /// Live (the user signs every reply) or delegated (Call for me).
    let mode: CallMode
    var captions: [Line]
    /// The Call for me notes (outcome, offers, answers, transcript and Bolna's summary), once
    /// loaded; updated when Bolna's summary arrives later.
    var notes: CallNotes?
}

extension CallRecord.Line {
    init(_ caption: Caption) {
        let speaker: Speaker = switch caption.speaker {
        case .receptionist: .receptionist
        case .agent: .agent
        case .user: .user
        }
        self.init(speaker: speaker, text: caption.text, at: caption.at)
    }
}
