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

/// Who said a captioned line. `agent` lines are lines the call agent says without a SEND
/// (the opening disclosure, the holding line, the goodbye, a delegated call's own lines).
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
    /// The agent runs the call from the typed request; the user may step in at any moment
    /// by typing or signing. With the call screen in front, each agent line is proposed
    /// first and spoken when its window runs out; away, lines are spoken at once.
    case steer
}

/// Body of `POST /calls` (`StartCallRequest`). Exactly one of `contactID` and `phoneNumber`:
/// a pasted number is dialled only when the backend's allowlist holds it. A delegated or
/// steer call needs `briefID`; `attended` lets a delegated agent ask the user yes/no/wait or
/// "when?" (time word) questions during the call.
public struct StartCallRequest: Codable, Equatable, Sendable {
    public var contactID: String?
    public var phoneNumber: String?
    public var purpose: CallPurpose
    public var mode: CallMode
    public var briefID: String?
    public var attended: Bool

    public init(
        contactID: String? = nil, phoneNumber: String? = nil, purpose: CallPurpose,
        mode: CallMode = .live, briefID: String? = nil, attended: Bool = false
    ) {
        self.contactID = contactID
        self.phoneNumber = phoneNumber
        self.purpose = purpose
        self.mode = mode
        self.briefID = briefID
        self.attended = attended
    }

    enum CodingKeys: String, CodingKey {
        case contactID = "contact_id"
        case phoneNumber = "phone_number"
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

/// One fact the user approved for sharing ("Date of birth" → "12 March 1998"). The agent
/// says it only when the receptionist asks for something its label names.
public struct Detail: Codable, Equatable, Hashable, Sendable {
    public var label: String
    public var value: String

    public init(label: String, value: String) {
        self.label = label
        self.value = value
    }
}

/// The text of a card, letter or bill the user attached, read on their phone. The agent may
/// quote from it when asked, word for word only; it never volunteers it.
public struct Document: Codable, Equatable, Hashable, Sendable {
    public var name: String
    public var text: String

    public init(name: String, text: String) {
        self.name = name
        self.text = text
    }
}

/// What the agent may share about the caller; nothing else is ever said.
public struct Profile: Codable, Equatable, Sendable {
    public var name: String
    public var callback: String?
    public var notes: String?
    public var details: [Detail]
    /// Omitted from the JSON when there are none, so older briefs are byte-for-byte the same.
    public var documents: [Document]?

    public init(name: String, callback: String? = nil, notes: String? = nil, details: [Detail] = [], documents: [Document] = []) {
        self.name = name
        self.callback = callback
        self.notes = notes
        self.details = details
        self.documents = documents.isEmpty ? nil : documents
    }
}

/// Body of `POST /briefs`. `request` is what the user typed the call is about (steer calls);
/// its days and parts of day are the only times the agent may agree to.
public struct BriefRequest: Codable, Equatable, Sendable {
    public var purpose: CallPurpose
    public var chips: [Sign]
    public var profile: Profile
    public var request: String?

    public init(purpose: CallPurpose, chips: [Sign], profile: Profile, request: String? = nil) {
        self.purpose = purpose
        self.chips = chips
        self.profile = profile
        self.request = request
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
    /// Steer calls: what the receptionist asked for that the request didn't carry, and how
    /// many times the user stepped in. Older backends omit both.
    public var followUps: [String]
    public var steppedIn: Int

    public init(
        callID: String, mode: CallMode, ready: Bool, brief: String? = nil, outcome: String? = nil,
        summary: [String] = [], openQuestions: [String] = [], transcript: [TranscriptEntry] = [],
        bolnaSummary: String? = nil, followUps: [String] = [], steppedIn: Int = 0
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
        self.followUps = followUps
        self.steppedIn = steppedIn
    }

    enum CodingKeys: String, CodingKey {
        case callID = "call_id"
        case mode, ready, brief, outcome, summary, transcript
        case openQuestions = "open_questions"
        case bolnaSummary = "bolna_summary"
        case followUps = "follow_ups"
        case steppedIn = "stepped_in"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        callID = try container.decode(String.self, forKey: .callID)
        mode = try container.decode(CallMode.self, forKey: .mode)
        ready = try container.decode(Bool.self, forKey: .ready)
        brief = try container.decodeIfPresent(String.self, forKey: .brief)
        outcome = try container.decodeIfPresent(String.self, forKey: .outcome)
        summary = try container.decodeIfPresent([String].self, forKey: .summary) ?? []
        openQuestions = try container.decodeIfPresent([String].self, forKey: .openQuestions) ?? []
        transcript = try container.decodeIfPresent([TranscriptEntry].self, forKey: .transcript) ?? []
        bolnaSummary = try container.decodeIfPresent(String.self, forKey: .bolnaSummary)
        followUps = try container.decodeIfPresent([String].self, forKey: .followUps) ?? []
        steppedIn = try container.decodeIfPresent(Int.self, forKey: .steppedIn) ?? 0
    }
}

// MARK: - Steer calls

/// Who wrote a proposed line: the agent (spoken when its window runs out) or the user (the
/// polished form of what they typed, previewed briefly).
public enum ProposalOrigin: String, Codable, Sendable {
    case agent
    case user
}

/// How a proposal's window ended.
public enum ProposalOutcome: String, Codable, Sendable {
    case spoken
    case held
    case cancelled
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
    /// Steer: whether the call screen is in front on an unlocked phone.
    case presence(present: Bool)
    /// Steer: the user started composing (`composing` true), dropping the proposed line, or
    /// backed out (`false`), so the held line is spoken after all.
    case hold(turnID: TurnID, composing: Bool)
    /// Steer: a line the user typed, to be polished, previewed and spoken.
    case say(text: String)
}

extension AppMessage: Encodable {
    enum CodingKeys: String, CodingKey {
        case type
        case turnID = "turn_id"
        case chips
        case text
        case askID = "ask_id"
        case choice
        case present
        case composing
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        switch self {
        case let .presence(present):
            try container.encode("presence", forKey: .type)
            try container.encode(present, forKey: .present)
        case let .hold(turnID, composing):
            try container.encode("hold", forKey: .type)
            try container.encode(turnID, forKey: .turnID)
            try container.encode(composing, forKey: .composing)
        case let .say(text):
            try container.encode("say", forKey: .type)
            try container.encode(text, forKey: .text)
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
    /// Steer: a line about to be spoken, with the seconds the user has to step in.
    case proposal(turnID: TurnID, text: String, windowS: Double, origin: ProposalOrigin)
    /// Steer: the proposal's window ended.
    case proposalResolved(turnID: TurnID, outcome: ProposalOutcome)
    /// Steer: the receptionist asked for something the request didn't carry; the agent
    /// deferred it and the notes will list it.
    case followUp(text: String)
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
        case windowS = "window_s"
        case origin
        case outcome
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let type = try container.decode(String.self, forKey: .type)
        switch type {
        case "proposal":
            self = .proposal(
                turnID: try container.decode(TurnID.self, forKey: .turnID),
                text: try container.decode(String.self, forKey: .text),
                windowS: try container.decode(Double.self, forKey: .windowS),
                origin: try container.decodeIfPresent(ProposalOrigin.self, forKey: .origin) ?? .agent)
        case "proposal_resolved":
            self = .proposalResolved(
                turnID: try container.decode(TurnID.self, forKey: .turnID),
                outcome: try container.decode(ProposalOutcome.self, forKey: .outcome))
        case "follow_up":
            self = .followUp(text: try container.decode(String.self, forKey: .text))
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
