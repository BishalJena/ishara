import CAndroidBridge
import Foundation
import RecognitionCore

let coreVersion = "IsharaCore 0.1.0 (logits bundle v\(LogitsBundle.supportedVersion))"

struct EchoEvent: Encodable {
    let type = "echo"
    let echo: String
    let onMainThread: Bool
}

struct QualityInput: Decodable {
    let poseFraction: Double
    let handFraction: Double
}

struct LogitsMatchOutput: Encodable {
    struct Candidate: Encodable {
        let gloss: String
        let p: Double
    }

    let kind: String
    var label: String?
    var p: Double?
    var margin: Double?
    var reason: String?
    let top: [Candidate]

    init(_ result: LogitsMatchResult) {
        func candidates(_ top: [LogitsCandidate]) -> [Candidate] {
            top.map { Candidate(gloss: $0.gloss, p: $0.p) }
        }
        switch result {
        case let .chip(label, p, margin, top):
            kind = "chip"
            self.label = label.rawValue
            self.p = p
            self.margin = margin
            self.top = candidates(top)
        case let .pickOne(label, p, margin, top):
            kind = "pickOne"
            self.label = label.rawValue
            self.p = p
            self.margin = margin
            self.top = candidates(top)
        case let .unsure(reason, top):
            kind = "unsure"
            self.reason = reason
            self.top = candidates(top)
        }
    }
}

func matchLogits(bundleJSON: String, logitsJSON: String, qualityJSON: String) throws -> LogitsMatchOutput {
    let bundle = try LogitsBundle.load(from: Data(bundleJSON.utf8))
    let logits = try JSONDecoder().decode([Float].self, from: Data(logitsJSON.utf8))
    let quality = try JSONDecoder().decode(QualityInput.self, from: Data(qualityJSON.utf8))
    let clipQuality = ClipQuality(poseFraction: quality.poseFraction, handFraction: quality.handFraction)
    return LogitsMatchOutput(LogitsMatcher(bundle).match(logits: logits, quality: clipQuality))
}

func encodeJSON(_ value: some Encodable) -> String {
    // Only our own Encodable types reach here; a failure is a programmer error.
    String(decoding: try! JSONEncoder().encode(value), as: UTF8.self)
}
