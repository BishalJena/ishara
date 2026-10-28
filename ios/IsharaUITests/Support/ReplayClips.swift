import XCTest

/// One labelled clip of the replay set and what the app should show for it.
///
/// The whole-clip decision comes from `expected.csv` in the clip folder, as written by
/// `spikes/recognition/asl_summary.py --app <parity out> --csv <clips>/expected.csv` after
/// `IsharaTests/ASLParityHarness` ran on the same clips (columns
/// `word,source,top1,p1,margin,decision,decided_gloss`; decision chip, pick_one or abstain).
///
/// The app sees only the frames the start/stop detector cuts, not the whole clip, so a few
/// clips can legitimately land elsewhere. Each such clip is listed, with the reason, in the
/// optional `app-expected.csv` (`clip,app,reason`; app is `chip:<sign>`, `pick:<sign>`, `?`
/// or `nothing`), and that is what the test then expects instead.
struct ReplayClip: Equatable {
    /// The clip's file name without extension, which is also its replay menu entry.
    let name: String
    /// The intended sign, or `none` for a negative.
    let word: String
    /// What the parity harness decided on the whole clip.
    let wholeClip: ReplayOutcome
    /// What the app must show; nil when the detector must cut nothing (no result at all).
    let expected: ReplayOutcome?
    /// Why `expected` differs from `wholeClip`, when it does.
    let reason: String?

    var isNegative: Bool { word == "none" }

    static let expectationsFile = "expected.csv"
    static let differencesFile = "app-expected.csv"

    /// Every clip in `folder`'s expectations file except the calibration clip.
    static func load(from folder: URL) throws -> [ReplayClip] {
        let whole = try table(folder.appendingPathComponent(expectationsFile))
        let differencesURL = folder.appendingPathComponent(differencesFile)
        let differences = FileManager.default.fileExists(atPath: differencesURL.path) ? try table(differencesURL) : []
        var overrides: [String: (ReplayOutcome?, String)] = [:]
        for row in differences {
            overrides[row["clip", default: ""]] = (try ReplayOutcome.expectation(row["app", default: ""]), row["reason", default: ""])
        }
        let clips = try whole.compactMap { row -> ReplayClip? in
            let name = URL(fileURLWithPath: row["source", default: ""]).deletingPathExtension().lastPathComponent
            guard name != "rest" else { return nil }
            let decided = try ReplayOutcome(decision: row["decision", default: ""], gloss: row["decided_gloss", default: ""])
            let override = overrides.removeValue(forKey: name)
            return ReplayClip(name: name, word: row["word", default: ""], wholeClip: decided,
                              expected: override.map(\.0) ?? decided, reason: override?.1)
        }
        guard overrides.isEmpty else { throw ReplayClipError.unknownClips(overrides.keys.sorted()) }
        return clips
    }

    /// A small CSV reader: a header row, then plain comma-separated values (the last column
    /// may contain commas).
    static func table(_ url: URL) throws -> [[String: String]] {
        let lines = try String(contentsOf: url, encoding: .utf8).split(whereSeparator: \.isNewline)
        guard let header = lines.first?.split(separator: ",").map(String.init) else { throw ReplayClipError.empty(url.lastPathComponent) }
        return lines.dropFirst().map { line in
            let values = line.split(separator: ",", maxSplits: header.count - 1, omittingEmptySubsequences: false).map(String.init)
            return Dictionary(uniqueKeysWithValues: zip(header, values + Array(repeating: "", count: max(0, header.count - values.count))))
        }
    }
}

enum ReplayClipError: Error {
    case empty(String)
    case unknownDecision(String)
    case unknownClips([String])
}

/// What one sign attempt produced on screen.
enum ReplayOutcome: Equatable, CustomStringConvertible {
    /// A confident sign: a chip.
    case chip(String)
    /// A "Did you mean …?" tile, which counts only when tapped.
    case pickOne(String)
    /// A `[?]` chip; `handLeftFrame` when the framing hint came with it.
    case unsure(handLeftFrame: Bool)

    init(decision: String, gloss: String) throws {
        switch decision {
        case "chip": self = .chip(gloss)
        case "pick_one": self = .pickOne(gloss)
        case "abstain": self = .unsure(handLeftFrame: false)
        default: throw ReplayClipError.unknownDecision(decision)
        }
    }

    /// `chip:<sign>`, `pick:<sign>`, `?`, or `nothing` (nil).
    static func expectation(_ text: String) throws -> ReplayOutcome? {
        if text == "nothing" { return nil }
        if text == "?" { return .unsure(handLeftFrame: false) }
        let parts = text.split(separator: ":", maxSplits: 1).map(String.init)
        guard parts.count == 2 else { throw ReplayClipError.unknownDecision(text) }
        return try ReplayOutcome(decision: parts[0] == "pick" ? "pick_one" : parts[0], gloss: parts[1])
    }

    /// chip, pick-one or `?`: what the test compares, since the framing hint only explains a `?`.
    var category: String {
        switch self {
        case .chip: "chip"
        case .pickOne: "pick-one"
        case .unsure: "?"
        }
    }

    var gloss: String? {
        switch self {
        case .chip(let gloss), .pickOne(let gloss): gloss
        case .unsure: nil
        }
    }

    var description: String {
        switch self {
        case .chip(let gloss): "chip:\(gloss)"
        case .pickOne(let gloss): "pick:\(gloss)"
        case .unsure(let frame): frame ? "?(hand left frame)" : "?"
        }
    }
}

extension Optional where Wrapped == ReplayOutcome {
    var text: String { map(\.description) ?? "nothing" }
}

extension XCUIApplication {
    /// Plays a saved clip from the simulator's "Replay a sign" menu.
    func replay(_ clip: String, file: StaticString = #filePath, line: UInt = #line) {
        let menu = buttons["replayMenu"]
        XCTAssertTrue(menu.waitForExistence(timeout: 10), "no replay menu: are the clips in LocalAssets/SampleSigns?",
                      file: file, line: line)
        menu.tap()
        XCTAssertTrue(collectionViews.firstMatch.waitForExistence(timeout: 5), "the replay menu did not open", file: file, line: line)
        // A long menu scrolls and only lists the entries in view; scroll until the clip shows.
        let item = buttons[clip]
        let list = collectionViews.firstMatch
        for _ in 0..<15 where list.exists && !(item.exists && item.isHittable) {
            // Slow: a fast swipe flings past entries and can close the menu.
            list.swipeUp(velocity: .slow)
        }
        guard item.exists, item.isHittable else {
            XCTFail("\(clip) is not in the replay menu: copy the clip folder into ios/Ishara/LocalAssets/SampleSigns and rebuild",
                    file: file, line: line)
            return
        }
        item.tap()
    }

    var cameraPillLabel: String {
        let pill = element("camera.pill")
        return pill.exists ? pill.label : ""
    }

    /// Waits until the detector has cut and classified the replayed sign, then reads every
    /// result on screen. An empty list means the detector cut no accepted segment.
    func outcomes(timeout: TimeInterval = 15) -> [ReplayOutcome] {
        let deadline = Date().addingTimeInterval(timeout)
        var sawSigning = false
        var watchingSince: Date?
        while Date() < deadline {
            let label = cameraPillLabel
            if label.contains("Sign in progress") {
                sawSigning = true
                watchingSince = nil
            } else if sawSigning, label.contains("Watching") {
                watchingSince = watchingSince ?? Date()
                // The result follows the end of the sign straight away; leave time to draw it.
                if let since = watchingSince, Date().timeIntervalSince(since) > 1.5 { break }
            }
            Thread.sleep(forTimeInterval: 0.1)
        }
        let framing = element("call.framingHint").exists
        var results = buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'chip.'")).allElementsBoundByIndex.map { chip in
            let name = String(chip.identifier.dropFirst("chip.".count))
            return name == "unsure" ? ReplayOutcome.unsure(handLeftFrame: framing) : .chip(name)
        }
        let candidate = buttons["candidate.accept"]
        if candidate.exists, let sign = Self.candidateSign(in: candidate.label) {
            results.append(.pickOne(sign))
        }
        return results
    }

    /// "Did you mean tomorrow? Double tap to use it." → tomorrow.
    static func candidateSign(in label: String) -> String? {
        guard let start = label.range(of: "Did you mean "),
              let end = label.range(of: "?", range: start.upperBound..<label.endIndex) else { return nil }
        return String(label[start.upperBound..<end.lowerBound])
    }

    /// Removes the previous attempt's chips and tile so the next result stands alone.
    func clearAttempt() {
        let dismiss = buttons["candidate.dismiss"]
        if dismiss.exists { dismiss.tap() }
        let clear = buttons["call.clear"]
        if clear.exists, clear.isEnabled { clear.tap() }
        waitUntil("the chips to clear", timeout: 5) {
            buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'chip.'")).count == 0
        }
    }

    func screenshot(named name: String, in testCase: XCTestCase) {
        let attachment = XCTAttachment(screenshot: screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        testCase.add(attachment)
    }
}
