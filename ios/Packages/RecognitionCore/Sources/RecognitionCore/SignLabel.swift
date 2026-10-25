/// The sign vocabulary the backend accepts (backend/app/protocol.py SIGNS, decision D8).
/// Raw values are the labels used in recognition bundles: SignCLIP reference bundles use
/// the first twelve; the ASL logits bundle's vocabulary is a subset of all of them.
public enum SignLabel: String, CaseIterable, Codable, Sendable, Comparable {
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
    case please
    case now
    case wait
    case night
    case yesterday
    case later
    case can
    case `where`
    case who
    case why
    case have
    case finish
    case callonphone
    case sick
    case hungry
    case drink
    case water
    case home
    case go
    case see
    case hear
    case read

    /// Orders by raw label so ties break the same way as the Python matcher.
    public static func < (lhs: SignLabel, rhs: SignLabel) -> Bool {
        lhs.rawValue < rhs.rawValue
    }
}
