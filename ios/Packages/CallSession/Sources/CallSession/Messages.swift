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

/// Who wrote a backend draft.
public enum DraftSource: String, Codable, CaseIterable, Sendable {
    case llm
    case template
}

// MARK: - REST

/// Body of `POST /calls` (`StartCallRequest`).
public struct StartCallRequest: Codable, Equatable, Sendable {
    public var contactID: String
    public var purpose: CallPurpose

    public init(contactID: String, purpose: CallPurpose) {
        self.contactID = contactID
        self.purpose = purpose
    }

    enum CodingKeys: String, CodingKey {
        case contactID = "contact_id"
        case purpose
    }
}

/// Response of `POST /calls` (`StartCallResponse`).
public struct CallStart: Codable, Equatable, Sendable {
    public var callID: String
    public var state: CallState

    public init(callID: String, state: CallState) {
        self.callID = callID
        self.state = state
    }

    enum CodingKeys: String, CodingKey {
        case callID = "call_id"
        case state
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
}

extension AppMessage: Encodable {
    enum CodingKeys: String, CodingKey {
        case type
        case turnID = "turn_id"
        case chips
        case text
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
        }
    }
}

// MARK: - Backend -> app (WebSocket)

/// Messages the backend sends on the call WebSocket.
public enum ServerMessage: Equatable, Sendable {
    case status(CallState)
    /// The receptionist's words. `at` is unix time in seconds.
    case caption(text: String, at: Double)
    case draft(turnID: TurnID, text: String, source: DraftSource)
    /// Bolna has spoken the approved reply for this turn.
    case spoken(turnID: TurnID)
    /// No `spoken` confirmation arrived in time. The backend never resends on its own.
    case notDelivered(turnID: TurnID, reason: String)
    case error(code: String, message: String)
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
        case turnID = "turn_id"
        case source
        case reason
        case code
        case message
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let type = try container.decode(String.self, forKey: .type)
        switch type {
        case "status":
            self = .status(try container.decode(CallState.self, forKey: .state))
        case "caption":
            self = .caption(
                text: try container.decode(String.self, forKey: .text),
                at: try container.decode(Double.self, forKey: .at))
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
