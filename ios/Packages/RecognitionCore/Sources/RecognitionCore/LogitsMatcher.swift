import Foundation

/// Decision D8: the public ASL Signs model gives 250 logits per clip; this is the
/// version-2 "asl-signs-logits" bundle (spikes/recognition/fixtures/asl/) and the open-set
/// rule that turns those logits into a chip, a pick-one candidate, or `?`. Mirrors
/// `load_asl_bundle` / `asl_decision` in spikes/recognition/asl_matcher.py; change both.
public enum LogitsBundleError: Error, Sendable, Equatable {
    case unsupportedVersion(Int)
    case unsupportedKind(String)
    case duplicateOrTooFewGlosses
    /// A vocabulary word the model has no class for.
    case vocabularyOutsideModel([String])
    /// A vocabulary word the backend does not accept as a `Sign`.
    case vocabularyOutsideBackend([String])
    case invalidThresholds
    case invalidQualityRequirements
    case perWordOutsideVocabulary([String])
}

public struct LogitsBundle: Codable, Sendable, Equatable {
    public static let supportedVersion = 2
    public static let supportedKind = "asl-signs-logits"

    public struct Model: Codable, Sendable, Equatable {
        public var name: String
        public var sha256: String
    }

    public struct Thresholds: Codable, Sendable, Equatable {
        /// Chip cut-off on the top-1 probability (overridden per word by `perWord`).
        public var p: Double
        /// Required gap between the top-1 and runner-up probabilities for a chip.
        public var margin: Double
        /// Below `p` but at or above this, a vocabulary top-1 is offered as a pick-one.
        public var pickOneP: Double

        enum CodingKeys: String, CodingKey {
            case p, margin
            case pickOneP = "pick_one_p"
        }
    }

    public var version: Int
    public var kind: String
    public var model: Model
    /// All 250 glosses in the model's output order.
    public var glosses: [String]
    /// The glosses that may become chips; everything else is the "something else" bucket.
    public var vocabulary: [String]
    public var thresholds: Thresholds
    public var perWord: [String: Double]
    public var quality: RecognitionBundle.QualityRequirements
    /// Probe defaults, not frozen on a labelled session. Shown as a banner, never hidden.
    public var provisional: Bool

    enum CodingKeys: String, CodingKey {
        case version, kind, model, glosses, vocabulary, thresholds, quality, provisional
        case perWord = "per_word"
    }

    public static func load(from data: Data) throws -> LogitsBundle {
        let bundle = try JSONDecoder().decode(LogitsBundle.self, from: data)
        try bundle.validate()
        return bundle
    }

    public func validate() throws(LogitsBundleError) {
        guard version == Self.supportedVersion else { throw .unsupportedVersion(version) }
        guard kind == Self.supportedKind else { throw .unsupportedKind(kind) }
        guard glosses.count >= 2, Set(glosses).count == glosses.count else { throw .duplicateOrTooFewGlosses }
        let outsideModel = vocabulary.filter { !glosses.contains($0) }
        guard outsideModel.isEmpty else { throw .vocabularyOutsideModel(outsideModel.sorted()) }
        let outsideBackend = vocabulary.filter { SignLabel(rawValue: $0) == nil }
        guard outsideBackend.isEmpty else { throw .vocabularyOutsideBackend(outsideBackend.sorted()) }
        let values = [thresholds.p, thresholds.margin, thresholds.pickOneP]
        guard values.allSatisfy({ $0.isFinite && (0...1).contains($0) }), thresholds.pickOneP <= thresholds.p
        else { throw .invalidThresholds }
        guard [quality.minPoseFraction, quality.minHandFraction].allSatisfy({ $0.isFinite && (0...1).contains($0) })
        else { throw .invalidQualityRequirements }
        let strayPerWord = perWord.keys.filter { !vocabulary.contains($0) }
        guard strayPerWord.isEmpty else { throw .perWordOutsideVocabulary(strayPerWord.sorted()) }
    }

    public func chipCutoff(for gloss: String) -> Double {
        perWord[gloss] ?? thresholds.p
    }
}

/// One ranked candidate: a gloss and its softmax probability.
public struct LogitsCandidate: Sendable, Equatable {
    public let gloss: String
    public let p: Double
}

public enum LogitsMatchResult: Sendable, Equatable {
    /// Confident vocabulary word: becomes a chip.
    case chip(label: SignLabel, p: Double, margin: Double, top: [LogitsCandidate])
    /// Vocabulary word in the grey zone: shown as a tile the user must tap; never a chip by itself.
    case pickOne(label: SignLabel, p: Double, margin: Double, top: [LogitsCandidate])
    /// Shown as `?` and never spoken. The reason is for the UI and the logs only.
    case unsure(reason: String, top: [LogitsCandidate])
}

public struct LogitsMatcher: Sendable {
    public let bundle: LogitsBundle
    public static let topK = 3

    public init(_ bundle: LogitsBundle) {
        self.bundle = bundle
    }

    /// Softmax over the raw logits; `nil` for a wrong length or non-finite values.
    public static func softmax(_ logits: [Float]) -> [Double]? {
        guard !logits.isEmpty, logits.allSatisfy(\.isFinite) else { return nil }
        let maximum = Double(logits.max()!)
        let exps = logits.map { exp(Double($0) - maximum) }
        let total = exps.reduce(0, +)
        return exps.map { $0 / total }
    }

    /// The open-set rule over the full probability vector. Never restricts to the
    /// vocabulary first: a confident non-vocabulary top-1 is `?`, not the best vocabulary word.
    public func match(logits: [Float], quality: ClipQuality) -> LogitsMatchResult {
        guard logits.count == bundle.glosses.count, let probs = Self.softmax(logits) else {
            return .unsure(reason: "invalid evidence", top: [])
        }
        let order = probs.indices.sorted { probs[$0] != probs[$1] ? probs[$0] > probs[$1] : $0 < $1 }
        let top = order.prefix(Self.topK).map { LogitsCandidate(gloss: bundle.glosses[$0], p: probs[$0]) }
        let gloss = bundle.glosses[order[0]]
        let p1 = probs[order[0]]
        let margin = p1 - probs[order[1]]

        var failed: [String] = []
        if quality.poseFraction < bundle.quality.minPoseFraction { failed.append("pose") }
        if quality.handFraction < bundle.quality.minHandFraction { failed.append("hands") }
        if !failed.isEmpty {
            return .unsure(reason: "tracking: " + failed.joined(separator: ", "), top: top)
        }
        guard bundle.vocabulary.contains(gloss), let label = SignLabel(rawValue: gloss) else {
            return .unsure(reason: "not in vocabulary: \(gloss) \(Self.format(p1))", top: top)
        }
        if p1 >= bundle.chipCutoff(for: gloss), margin >= bundle.thresholds.margin {
            return .chip(label: label, p: p1, margin: margin, top: top)
        }
        if p1 >= bundle.thresholds.pickOneP {
            return .pickOne(label: label, p: p1, margin: margin, top: top)
        }
        return .unsure(reason: "unsure: \(gloss) \(Self.format(p1))", top: top)
    }

    private static func format(_ value: Double) -> String {
        String(format: "%.2f", value)
    }
}
