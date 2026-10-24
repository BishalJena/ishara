/// The demo vocabulary (PLAN.md §5). Raw values are the labels used in exported
/// recognition bundles, so a reference outside this set cannot be represented.
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

    /// Orders by raw label so ties break the same way as the Python matcher.
    public static func < (lhs: SignLabel, rhs: SignLabel) -> Bool {
        lhs.rawValue < rhs.rawValue
    }
}
