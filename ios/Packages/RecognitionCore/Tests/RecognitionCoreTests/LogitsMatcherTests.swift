import XCTest

@testable import RecognitionCore

/// Mirrors spikes/recognition/test_asl_matcher.py on the same fixture.
final class LogitsMatcherTests: XCTestCase {
    static let bundle: LogitsBundle = {
        let url = Bundle.module.url(
            forResource: "asl-bundle-provisional", withExtension: "json", subdirectory: "Fixtures/asl")!
        return try! LogitsBundle.load(from: Data(contentsOf: url))
    }()
    let good = ClipQuality(poseFraction: 1.0, handFraction: 0.9)
    var matcher: LogitsMatcher { LogitsMatcher(Self.bundle) }

    /// Logits whose softmax gives the named glosses these probabilities; the rest share the remainder.
    func logits(_ mass: [String: Double]) -> [Float] {
        let glosses = Self.bundle.glosses
        let rest = (1.0 - mass.values.reduce(0, +)) / Double(glosses.count - mass.count)
        return glosses.map { gloss in Float(log(mass[gloss] ?? rest)) }
    }

    func testFixtureIsConsistentWithTheBackendVocabulary() {
        XCTAssertEqual(Self.bundle.glosses.count, 250)
        XCTAssertTrue(Self.bundle.provisional)
        XCTAssertTrue(Self.bundle.vocabulary.allSatisfy { SignLabel(rawValue: $0) != nil })
    }

    func testOnlyTheRehearsedWordsMinusMorningMayChip() {
        // MORNING is held back: the model learned its one-handed form (iPhone test pending).
        XCTAssertEqual(Set(Self.bundle.vocabulary),
                       ["hello", "thankyou", "yes", "no", "now", "please", "tomorrow", "wait"])
    }

    func testThresholdsAreTheProvisionalPublicClipCandidate() {
        XCTAssertTrue(Self.bundle.provisional, "the iPhone clips decide the final values")
        XCTAssertEqual(Self.bundle.thresholds, .init(p: 0.65, margin: 0.3, pickOneP: 0.35))
        XCTAssertEqual(Self.bundle.perWord, ["hello": 0.5, "no": 0.45, "now": 0.45, "thankyou": 0.6,
                                             "tomorrow": 0.45, "wait": 0.45, "yes": 0.5])
    }

    func testFixtureIsTheMacBundle() throws {
        // spikes/recognition/fixtures/asl is what the Mac bridge loads; this copy must match it.
        let mac = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("spikes/recognition/fixtures/asl/asl-bundle-provisional.json")
        XCTAssertEqual(try LogitsBundle.load(from: Data(contentsOf: mac)), Self.bundle)
    }

    func testConfidentVocabularyWordIsAChip() {
        guard case let .chip(label, p, _, top) = matcher.match(logits: ["tomorrow": 0.72, "yourself": 0.1], quality: good)
        else { return XCTFail("expected a chip") }
        XCTAssertEqual(label, .tomorrow)
        XCTAssertEqual(p, 0.72, accuracy: 1e-6)
        XCTAssertEqual(top.first?.gloss, "tomorrow")
    }

    func testGreyZoneIsPickOneNotAChip() {
        guard case let .pickOne(label, _, _, _) = matcher.match(logits: ["tomorrow": 0.45, "yourself": 0.3], quality: good)
        else { return XCTFail("expected pick-one") }
        XCTAssertEqual(label, .tomorrow)
    }

    func testConfidentButSmallMarginIsPickOne() {
        guard case .pickOne = matcher.match(logits: ["no": 0.5, "yes": 0.45], quality: good)
        else { return XCTFail("expected pick-one") }
    }

    func testConfidentNonVocabularyWordIsUnsureNeverAChip() {
        // The ISLRTC "no" read as ASL "bye" at 0.88; the other classes are the reject bucket.
        guard case let .unsure(reason, _) = matcher.match(logits: ["bye": 0.88], quality: good)
        else { return XCTFail("expected unsure") }
        XCTAssertTrue(reason.hasPrefix("not in vocabulary: bye"))
    }

    func testConfidentUnrehearsedWordIsNeverAChipOrATile() {
        // Public-clip Gate 2: YES read as can, WAIT as hungry, a portrait YES as time.
        for gloss in ["can", "hungry", "time"] {
            for p in [0.9, 0.5] {
                guard case let .unsure(reason, _) = matcher.match(logits: [gloss: p], quality: good)
                else { return XCTFail("\(gloss) at \(p) must be unsure") }
                XCTAssertTrue(reason.hasPrefix("not in vocabulary: \(gloss)"), reason)
            }
        }
    }

    func testYesReadAsCanIsUnsureNotTheRunnerUpYes() {
        guard case .unsure = matcher.match(logits: ["can": 0.62, "yes": 0.3], quality: good)
        else { return XCTFail("expected unsure") }
    }

    func testMorningIsNeverAChipOrATile() {
        for p in [0.95, 0.5] {
            guard case .unsure = matcher.match(logits: ["morning": p], quality: good)
            else { return XCTFail("morning at \(p) must be unsure") }
        }
    }

    func testShippedCutoffsPerWordAndGlobal() {
        guard case .chip = matcher.match(logits: ["tomorrow": 0.46], quality: good) else { return XCTFail("tomorrow 0.46") }
        guard case .pickOne = matcher.match(logits: ["tomorrow": 0.44], quality: good) else { return XCTFail("tomorrow 0.44") }
        guard case .chip = matcher.match(logits: ["please": 0.66], quality: good) else { return XCTFail("please 0.66") }
        guard case .pickOne = matcher.match(logits: ["please": 0.64], quality: good) else { return XCTFail("please 0.64") }
    }

    func testRestrictingToTheVocabularyFirstWouldHaveBeenWrong() {
        // ISL "evening" clips: flat output with the best vocabulary word at p 0.01.
        guard case .unsure = matcher.match(logits: ["vacuum": 0.12, "pool": 0.1, "no": 0.01], quality: good)
        else { return XCTFail("expected unsure") }
    }

    func testFlatOutputIsUnsure() {
        guard case .unsure = matcher.match(logits: Array(repeating: 0, count: 250), quality: good)
        else { return XCTFail("expected unsure") }
    }

    func testPoorTrackingAbstainsEvenWhenConfident() {
        guard case let .unsure(reason, _) = matcher.match(
            logits: ["hello": 0.95], quality: ClipQuality(poseFraction: 0.3, handFraction: 0.9))
        else { return XCTFail("expected unsure") }
        XCTAssertTrue(reason.contains("pose"))
    }

    func testPerWordCutoffOverridesTheGlobalOne() throws {
        var tuned = Self.bundle
        tuned.perWord = ["tomorrow": 0.45]
        try tuned.validate()
        let tunedMatcher = LogitsMatcher(tuned)
        guard case .chip = tunedMatcher.match(logits: logits(["tomorrow": 0.5, "another": 0.1]), quality: good)
        else { return XCTFail("tomorrow at 0.5 should be a chip with the per-word cut-off") }
        guard case .pickOne = tunedMatcher.match(logits: logits(["please": 0.5, "another": 0.1]), quality: good)
        else { return XCTFail("please at 0.5 stays pick-one") }
    }

    func testInvalidVectorsAreUnsure() {
        guard case let .unsure(reason, _) = matcher.match(logits: [1, 2, 3], quality: good)
        else { return XCTFail("expected unsure") }
        XCTAssertEqual(reason, "invalid evidence")
        var bad = logits(["hello": 0.9])
        bad[0] = .nan
        guard case .unsure(reason: "invalid evidence", _) = matcher.match(logits: bad, quality: good)
        else { return XCTFail("NaN must be invalid evidence") }
    }

    func testBundleValidationRejectsVocabularyOutsideTheModelOrBackend() throws {
        var outsideModel = Self.bundle
        outsideModel.vocabulary.append("doctor")  // a backend sign, not one of the 250
        XCTAssertThrowsError(try outsideModel.validate()) {
            XCTAssertEqual($0 as? LogitsBundleError, .vocabularyOutsideModel(["doctor"]))
        }
        var outsideBackend = Self.bundle
        outsideBackend.vocabulary.append("zebra")  // one of the 250, not a backend sign
        XCTAssertThrowsError(try outsideBackend.validate()) {
            XCTAssertEqual($0 as? LogitsBundleError, .vocabularyOutsideBackend(["zebra"]))
        }
        var wrongKind = Self.bundle
        wrongKind.kind = "signclip-references"
        XCTAssertThrowsError(try wrongKind.validate())
    }

    func testSoftmaxSumsToOne() {
        let p = LogitsMatcher.softmax([2, 0, -1])!
        XCTAssertEqual(p.reduce(0, +), 1, accuracy: 1e-9)
        XCTAssertEqual(p.indices.max { p[$0] < p[$1] }, 0)
    }
}

private extension LogitsMatcher {
    func match(logits mass: [String: Double], quality: ClipQuality) -> LogitsMatchResult {
        let glosses = bundle.glosses
        let rest = (1.0 - mass.values.reduce(0, +)) / Double(glosses.count - mass.count)
        return match(logits: glosses.map { Float(log(mass[$0] ?? rest)) }, quality: quality)
    }
}
