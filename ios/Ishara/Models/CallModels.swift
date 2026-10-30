import CallSession
import Foundation

// Turn state (chips, drafts, turn ids, captions, quick replies) comes from CallSession's
// TurnStore, the single source of truth for the SEND safety rules. This file only adds
// what the screens need on top.

/// What the camera pill shows.
enum CameraState: Equatable, Sendable {
    /// Hands at rest, ready for the next sign (green).
    case watching
    /// A sign is in progress (yellow).
    case signing
    /// Face or hands not visible (red).
    case cantSee
}

/// The badge on the draft card, saying where the sentence came from.
enum DraftBadge: Equatable, Sendable {
    case llm, template, quickReply
    /// The last reply wasn't spoken; SEND offers it again on a new turn.
    case notDelivered
    /// The user stopped the last reply before it was spoken; SEND offers it again.
    case stopped

    init(_ origin: Draft.Origin) {
        switch origin {
        case .llm: self = .llm
        case .template: self = .template
        case .quickReply: self = .quickReply
        }
    }

    var title: String {
        switch self {
        case .llm: "LLM"
        case .template: "Template"
        case .quickReply: "Quick reply"
        case .notDelivered: "Not delivered"
        case .stopped: "Stopped"
        }
    }
}

/// The sentence the draft card shows and SEND would speak.
struct DraftDisplay: Equatable, Sendable {
    let text: String
    let badge: DraftBadge
}

extension Chip {
    /// The sign's word ("thankyou"), or "?" for an unsure sign.
    var label: String { sign?.rawValue ?? "?" }
    /// What the chip shows: the word as written ("thank you").
    var title: String { label == "thankyou" ? "thank you" : label }
}

extension QuickReply {
    var label: String {
        switch self {
        case .yes: "Yes"
        case .no: "No"
        case .wait: "Wait"
        case .repeat: "Repeat"
        }
    }
}
