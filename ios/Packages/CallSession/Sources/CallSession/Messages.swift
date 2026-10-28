import Foundation

// Swift mirror of backend/app/protocol.py. JSON keys are snake_case and every WebSocket
// message carries a `type` discriminator. Change both sides together.

/// `CallState` in the backend.
public enum CallState: String, Codable, CaseIterable, Sendable {
    case dialing
    case ringing
    case inCall = "in_call"
    case speaking
    case ended
    case error
}

/// Who said a captioned line. `agent` lines are fixed lines the call agent says without a
/// SEND (the opening disclosure, the holding line, the goodbye).
public enum CaptionSpeaker: String, Codable, CaseIterable, Sendable {
    case receptionist
    case agent
}

/// Who wrote a backend draft.
public enum DraftSource: String, Codable, CaseIterable, Sendable {
    case llm
    case template
}

// MARK: - REST

/// Decision D9. `live`: every sentence is composed from signs and approved with SEND.
/// `delegated`: the agent pursues a brief the user approved once (by starting the call).
public enum CallMode: String, Codable, CaseIterable, Sendable {
    case live
    case delegated
}

/// Body of `POST /calls` (`StartCallRequest`). A delegated call needs `briefID`; `attended`
/// lets the agent ask the user yes/no/wait or "when?" (time word) questions during the call.
public struct StartCallRequest: Codable, Equatable, Sendable {
    public var contactID: String
    public var purpose: CallPurpose
    public var mode: CallMode
    public var briefID: String?
    public var attended: Bool

    public init(
        contactID: String, purpose: CallPurpose, mode: CallMode = .live, briefID: String? = nil,
        attended: Bool = false
    ) {
        self.contactID = contactID
        self.purpose = purpose
        self.mode = mode
        self.briefID = briefID
        self.attended = attended
    }

    enum CodingKeys: String, CodingKey {
        case contactID = "contact_id"
        case purpose, mode, attended
        case briefID = "brief_id"
    }
}

/// Response of `POST /calls` (`StartCallResponse`). Older backends omit `mode`.
public struct CallStart: Codable, Equatable, Sendable {
    public var callID: String
    public var state: CallState
    public var mode: CallMode

    public init(callID: String, state: CallState, mode: CallMode = .live) {
        self.callID = callID
        self.state = state
        self.mode = mode
    }

    enum CodingKeys: String, CodingKey {
        case callID = "call_id"
        case state, mode
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        callID = try container.decode(String.self, forKey: .callID)
        state = try container.decode(CallState.self, forKey: .state)
        mode = try container.decodeIfPresent(CallMode.self, forKey: .mode) ?? .live
    }
}

// MARK: - Delegated calls (D9)

/// What the agent may share about the caller; nothing else is ever said.
public struct Profile: Codable, Equatable, Sendable {
    public var name: String
    public var callback: String?
    public var notes: String?

    public init(name: String, callback: String? = nil, notes: String? = nil) {
        self.name = name
        self.callback = callback
        self.notes = notes
    }
}

/// Body of `POST /briefs`.
public struct BriefRequest: Codable, Equatable, Sendable {
    public var purpose: CallPurpose
    public var chips: [Sign]
    public var profile: Profile

    public init(purpose: CallPurpose, chips: [Sign], profile: Profile) {
        self.purpose = purpose
        self.chips = chips
        self.profile = profile
    }
}

/// Response of `POST /briefs`: `text` is what the user approves; the agent pursues exactly it.
public struct Brief: Codable, Equatable, Sendable {
    public var briefID: String
    public var text: String
    public var goal: String
    public var constraints: [String]

    public init(briefID: String, text: String, goal: String, constraints: [String]) {
        self.briefID = briefID
        self.text = text
        self.goal = goal
        self.constraints = constraints
    }

    enum CodingKeys: String, CodingKey {
        case briefID = "brief_id"
        case text, goal, constraints
    }
}

/// An answer to the agent's question on an attended delegated call: yes / no / wait for an
/// offered time, or a time word for an open "when?" question. Each is also a `Sign`, so a
/// recognised chip equal to an option's choice answers it. Mirrors the backend's `AskChoice`
/// (backend/app/protocol.py); change both together.
public enum AskChoice: String, Codable, CaseIterable, Sendable {
    case yes, no, wait, tomorrow, morning, now
}

public struct AskOption: Codable, Equatable, Sendable {
    public var choice: AskChoice
    /// Exactly what the agent will say if this is chosen.
    public var spoken: String

    public init(choice: AskChoice, spoken: String) {
        self.choice = choice
        self.spoken = spoken
    }
}

public struct TranscriptEntry: Codable, Equatable, Sendable {
    public var speaker: CaptionSpeaker
    public var text: String
    public var at: Double

    public init(speaker: CaptionSpeaker, text: String, at: Double) {
        self.speaker = speaker
        self.text = text
        self.at = at
    }
}

/// Response of `GET /calls/{id}/notes`.
public struct CallNotes: Codable, Equatable, Sendable {
    public var callID: String
    public var mode: CallMode
    public var ready: Bool
    public var brief: String?
    public var outcome: String?
    public var summary: [String]
    public var openQuestions: [String]
    public var transcript: [TranscriptEntry]
    public var bolnaSummary: String?

    public init(
        callID: String, mode: CallMode, ready: Bool, brief: String? = nil, outcome: String? = nil,
        summary: [String] = [], openQuestions: [String] = [], transcript: [TranscriptEntry] = [],
        bolnaSummary: String? = nil
    ) {
        self.callID = callID
        self.mode = mode
        self.ready = ready
        self.brief = brief
        self.outcome = outcome
        self.summary = summary
        self.openQuestions = openQuestions
        self.transcript = transcript
        self.bolnaSummary = bolnaSummary
    }

    enum CodingKeys: String, CodingKey {
        case callID = "call_id"
        case mode, ready, brief, outcome, summary, transcript
        case openQuestions = "open_questions"
        case bolnaSummary = "bolna_summary"
    }
}

// MARK: - App -> backend (WebSocket)

/// Messages the app sends on the call WebSocket.
public enum AppMessage: Equatable, Sendable {
    /// Chips changed; the backend recomposes the draft for `turnID`.
    case chips(turnID: TurnID, chips: [Sign])
    /// The user tapped SEND with exactly this text. Single use per turn id.
    case approve(turnID: TurnID, text: String)
    /// Cancel unspoken output.
    case stop
    /// End the call.
    case end
    /// Answer the agent's open question on an attended delegated call (D9).
    case answer(askID: String, choice: AskChoice)
}

extension AppMessage: Encodable {
    enum CodingKeys: String, CodingKey {
        case type
        case turnID = "turn_id"
        case chips
        case text
        case askID = "ask_id"
        case choice
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        switch self {
        case let .chips(turnID, chips):
            try container.encode("chips", forKey: .type)
            try container.encode(turnID, forKey: .turnID)
            try container.encode(chips, forKey: .chips)
        case let .approve(turnID, text):
            try container.encode("approve", forKey: .type)
            try container.encode(turnID, forKey: .turnID)
            try container.encode(text, forKey: .text)
        case .stop:
            try container.encode("stop", forKey: .type)
        case .end:
            try container.encode("end", forKey: .type)
        case let .answer(askID, choice):
            try container.encode("answer", forKey: .type)
            try container.encode(askID, forKey: .askID)
            try container.encode(choice, forKey: .choice)
        }
    }
}

// MARK: - Backend -> app (WebSocket)

/// Messages the backend sends on the call WebSocket.
public enum ServerMessage: Equatable, Sendable {
    case status(CallState)
    /// A line said on the call: the receptionist's words, or a fixed agent line. `at` is
    /// unix time in seconds.
    case caption(text: String, at: Double, speaker: CaptionSpeaker = .receptionist)
    case draft(turnID: TurnID, text: String, source: DraftSource)
    /// Bolna has spoken the approved reply for this turn.
    case spoken(turnID: TurnID)
    /// No `spoken` confirmation arrived in time. The backend never resends on its own.
    case notDelivered(turnID: TurnID, reason: String)
    case error(code: String, message: String)
    /// Attended delegated call: the agent said "one moment, please" and needs the user's
    /// answer; after `timeoutS` with none, it says `fallback` instead.
    case ask(askID: String, question: String, options: [AskOption], fallback: String, timeoutS: Double)
    /// The question closed: what the agent said, and whether the user or the timeout decided.
    case askResolved(askID: String, spoken: String, source: String)
    /// A message type this app version doesn't know. Ignored rather than treated as a failure,
    /// so a newer backend can't crash an older app.
    case unknown(type: String)
}

extension ServerMessage: Decodable {
    enum CodingKeys: String, CodingKey {
        case type
        case state
        case text
        case at
        case speaker
        case turnID = "turn_id"
        case source
        case reason
        case code
        case message
        case askID = "ask_id"
        case question
        case options
        case fallback
        case timeoutS = "timeout_s"
        case spoken
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let type = try container.decode(String.self, forKey: .type)
        switch type {
        case "status":
            self = .status(try container.decode(CallState.self, forKey: .state))
        case "caption":
            // Older backends send no speaker; every caption was the receptionist's then.
            // An unknown speaker from a newer backend is shown as the receptionist rather
            // than dropping the line.
            let speaker = try container.decodeIfPresent(String.self, forKey: .speaker)
            self = .caption(
                text: try container.decode(String.self, forKey: .text),
                at: try container.decode(Double.self, forKey: .at),
                speaker: speaker.flatMap(CaptionSpeaker.init(rawValue:)) ?? .receptionist)
        case "draft":
            self = .draft(
                turnID: try container.decode(TurnID.self, forKey: .turnID),
                text: try container.decode(String.self, forKey: .text),
                source: try container.decode(DraftSource.self, forKey: .source))
        case "spoken":
            self = .spoken(turnID: try container.decode(TurnID.self, forKey: .turnID))
        case "not_delivered":
            self = .notDelivered(
                turnID: try container.decode(TurnID.self, forKey: .turnID),
                reason: try container.decode(String.self, forKey: .reason))
        case "error":
            self = .error(
                code: try container.decode(String.self, forKey: .code),
                message: try container.decode(String.self, forKey: .message))
        case "ask":
            self = .ask(
                askID: try container.decode(String.self, forKey: .askID),
                question: try container.decode(String.self, forKey: .question),
                options: try container.decode([AskOption].self, forKey: .options),
                fallback: try container.decode(String.self, forKey: .fallback),
                timeoutS: try container.decode(Double.self, forKey: .timeoutS))
        case "ask_resolved":
            self = .askResolved(
                askID: try container.decode(String.self, forKey: .askID),
                spoken: try container.decode(String.self, forKey: .spoken),
                source: try container.decode(String.self, forKey: .source))
        default:
            self = .unknown(type: type)
        }
    }
}

// MARK: - Coding

/// The JSON coders used on the wire. Sorted keys make the encoded bytes deterministic.
public enum WireCoding {
    public static func makeEncoder() -> JSONEncoder {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        return encoder
    }

    public static func encodeText(_ message: AppMessage) throws -> String {
        String(decoding: try makeEncoder().encode(message), as: UTF8.self)
    }

    public static func decodeServerMessage(_ text: String) throws -> ServerMessage {
        try JSONDecoder().decode(ServerMessage.self, from: Data(text.utf8))
    }
}
