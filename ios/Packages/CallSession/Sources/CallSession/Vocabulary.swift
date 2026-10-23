import Foundation

/// The 12 demo signs. Raw values are the backend's `Sign` literals (backend/app/protocol.py).
public enum Sign: String, Codable, CaseIterable, Sendable {
    case hello
    case thankyou
    case yes
    case no
    case sorry
    case doctor
    case today
    case tomorrow
    case morning
    case afternoon
    case evening
    case time
}

/// Why the call is being placed. Chosen on the Home screen, never signed.
public enum CallPurpose: String, Codable, CaseIterable, Sendable {
    case doctorAppointment = "doctor_appointment"
}

/// Limits the backend enforces; the app checks them first so it never sends a message
/// the backend would reject.
public enum ProtocolLimits {
    /// `MAX_CHIPS`: most chips one `chips` message may carry.
    public static let maxChips = 8
    /// `MAX_SPOKEN_CHARS`: longest text one `approve` may carry, counted in Unicode
    /// scalars to match Python's `len(str)`.
    public static let maxSpokenCharacters = 300
}

/// A client-generated turn id. Matches the backend pattern `^[A-Za-z0-9_-]{1,64}$`.
public struct TurnID: Hashable, Sendable, CustomStringConvertible {
    public let rawValue: String

    /// Returns nil when `rawValue` doesn't match the backend pattern.
    public init?(_ rawValue: String) {
        guard Self.isValid(rawValue) else { return nil }
        self.rawValue = rawValue
    }

    /// A fresh id: a UUID as 32 lowercase hex characters.
    public static func random() -> TurnID {
        let hex = UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()
        return TurnID(uncheckedRawValue: hex)
    }

    public var description: String { rawValue }

    static func isValid(_ value: String) -> Bool {
        let scalars = value.unicodeScalars
        guard (1...64).contains(scalars.count) else { return false }
        return scalars.allSatisfy { scalar in
            scalar.isASCII
                && (CharacterSet.alphanumerics.contains(scalar) || scalar == "_" || scalar == "-")
        }
    }

    private init(uncheckedRawValue: String) {
        rawValue = uncheckedRawValue
    }
}

extension TurnID: Codable {
    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        let raw = try container.decode(String.self)
        guard let id = TurnID(raw) else {
            throw DecodingError.dataCorruptedError(
                in: container, debugDescription: "turn_id \(raw) doesn't match ^[A-Za-z0-9_-]{1,64}$")
        }
        self = id
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(rawValue)
    }
}
