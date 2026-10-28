import XCTest

/// The local demo server's stdout (`backend/scripts/local_demo.py`), redirected to a file the
/// simulator's test runner can read. The stand-in Bolna prints each line it voices as
/// `agent says: <text>`, so these lines are exactly what a caller would hear.
struct LocalBackendLog {
    static let spokenPrefix = "agent says: "
    // backend/app/markers.py HOLDING_LINE: Bolna's silence repeat. It can fire during any
    // pause (PLAN §3), never carries the user's words, and so isn't a reply spoken before SEND.
    static let holdingLine = "One moment please, I'm signing my reply."

    let url: URL

    var text: String { (try? String(contentsOf: url, encoding: .utf8)) ?? "" }

    /// What the stand-in Bolna has spoken so far, minus the silence-repeat holding line.
    func spokenLines() -> [String] {
        text.split(separator: "\n").compactMap { line in
            line.range(of: Self.spokenPrefix).map { String(line[$0.upperBound...]) }
        }.filter { $0 != Self.holdingLine }
    }
}
