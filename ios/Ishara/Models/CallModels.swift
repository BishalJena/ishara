import Foundation

/// Identifies one reply turn. Approvals and drafts are tied to it so an old
/// draft or a repeated SEND can never be spoken for a newer turn.
typealias TurnID = Int

/// Call states the backend reports (`status {state}`, PLAN §3).
enum CallStatus: String, Equatable, Sendable {
    case dialing, ringing, inCall = "in_call", speaking, ended, error
}

/// Who wrote a draft. Shown as a badge so the user knows how it was made.
enum DraftSource: String, Equatable, Sendable {
    case llm, template, quickReply = "quick_reply"

    var badge: String {
        switch self {
        case .llm: "LLM"
        case .template: "Template"
        case .quickReply: "Quick reply"
        }
    }
}

struct Draft: Equatable, Sendable {
    let text: String
    let source: DraftSource
}

/// One recognition outcome from the on-device sign pipeline.
enum RecognitionResult: Equatable, Sendable {
    /// A sign matched one of the user's recorded examples closely enough.
    case sign(String)
    /// Something was signed but nothing matched well enough. Never spoken.
    case unsure
}

/// What the camera pill shows.
enum CameraState: Equatable, Sendable {
    /// Hands at rest, ready for the next sign (green).
    case watching
    /// A sign is in progress (yellow).
    case signing
    /// Face or hands not visible (red).
    case cantSee
}

struct Chip: Identifiable, Equatable, Sendable {
    enum Kind: Equatable, Sendable {
        case recognised(String)
        case unsure
    }

    let id: UUID
    let kind: Kind

    init(id: UUID = UUID(), kind: Kind) {
        self.id = id
        self.kind = kind
    }

    /// The sign's word, or nil for an unsure chip, which is never sent.
    var word: String? {
        if case .recognised(let word) = kind { word } else { nil }
    }
}

struct CaptionEntry: Identifiable, Equatable, Sendable {
    enum Speaker: Equatable, Sendable {
        case receptionist
        /// A reply the user approved and the call confirmed as spoken.
        case user
    }

    let id: UUID
    let speaker: Speaker
    let text: String
    let at: Date

    init(id: UUID = UUID(), speaker: Speaker, text: String, at: Date) {
        self.id = id
        self.speaker = speaker
        self.text = text
        self.at = at
    }
}

/// Full sentences the quick-reply buttons put into the draft. SEND is still needed.
enum QuickReply: String, CaseIterable, Identifiable, Sendable {
    case yes, no, wait, repeatThat

    var id: String { rawValue }

    var label: String {
        switch self {
        case .yes: "Yes"
        case .no: "No"
        case .wait: "Wait"
        case .repeatThat: "Repeat"
        }
    }

    var sentence: String {
        switch self {
        case .yes: "Yes."
        case .no: "No."
        case .wait: "Please wait a moment, I'm signing my reply."
        case .repeatThat: "Sorry, could you please repeat that?"
        }
    }
}
