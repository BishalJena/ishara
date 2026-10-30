import ActivityKit
import Foundation

/// The live call on the lock screen and in the Dynamic Island: who we're calling, the latest
/// line said, and who is driving. Shared by the app (which starts and updates it) and the
/// widget extension (which draws it).
struct CallActivityAttributes: ActivityAttributes {
    struct ContentState: Codable, Hashable {
        enum Driving: String, Codable {
            /// Ishara is speaking for the user; nobody is watching.
            case agent
            /// The user is typing or signing.
            case user
            /// Ringing or connecting.
            case connecting
            case ended
        }

        var latestLine: String
        var latestSpeakerIsUs: Bool
        var driving: Driving
        var startedAt: Date?
        var outcome: String?
    }

    let contactName: String
    let contactInitials: String
}
