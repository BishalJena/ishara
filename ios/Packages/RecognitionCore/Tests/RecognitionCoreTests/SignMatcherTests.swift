import RecognitionCore
import XCTest

final class SignMatcherTests: XCTestCase {
    private let good = ClipQuality(poseFraction: 1, handFraction: 1)

    /// Bundles are built in code (not validated) so tests can also feed the matcher
    /// banks that validation would refuse.
    private func bundle(
        _ references: [(SignLabel, [Float])],
        similarity: Double = 0.8,
        margin: Double = 0.05,
        quality: RecognitionBundle.QualityRequirements = .init(),
        dim: Int? = nil
    ) -> RecognitionBundle {
        RecognitionBundle(
            encoder: "test",
            embeddingDim: dim ?? references.first?.1.count ?? 3,
            thresholds: .init(similarity: similarity, margin: margin),
            quality: quality,
            references: references.enumerated().map { index, reference in
                .init(id: "r\(index)", label: reference.0, embedding: reference.1)
            }
        )
    }

    private var helloDoctor: [(SignLabel, [Float])] { [(.hello, [1, 0, 0]), (.doctor, [0, 1, 0])] }

    private struct NoBaseline: Error {
        let result: MatchResult
    }

    /// The scores the matcher computes for `query`, read with cut-offs that accept anything.
    private func similarityAndMargin(
        _ query: [Float],
        _ references: [(SignLabel, [Float])]
    ) throws -> (similarity: Double, margin: Double) {
        let permissive = SignMatcher(bundle(references, similarity: -1, margin: 0))
        let result = permissive.match(embedding: query, quality: good)
        guard case .sign(_, let similarity, let margin) = result else { throw NoBaseline(result: result) }
        return (similarity, margin)
    }

    // MARK: Accepting

    func testExactMatchIsAcceptedWithItsScores() {
        let result = SignMatcher(bundle(helloDoctor)).match(embedding: [1, 0, 0], quality: good)

        XCTAssertEqual(result, .sign(label: .hello, similarity: 1, margin: 1))
    }

    func testScoresMatchThePythonMatcher() {
        // Expected values from recognition_data.rank + decision on the same vectors.
        let references: [(SignLabel, [Float])] = [
            (.hello, [0.9, 0.3, -0.2, 0.1]), (.hello, [0.7, 0.5, 0.1, 0.0]),
            (.doctor, [0.1, 0.9, 0.4, -0.3]), (.morning, [-0.5, 0.2, 0.8, 0.4]),
        ]
        let matcher = SignMatcher(bundle(references, similarity: 0.9, margin: 0.05))

        guard case .sign(.hello, let s1, let m1) = matcher.match(embedding: [0.8, 0.4, 0.0, 0.05], quality: good)
        else { return XCTFail("expected hello") }
        XCTAssertEqual(s1, 0.979626, accuracy: 1e-6)
        XCTAssertEqual(m1, 0.520984, accuracy: 1e-6)

        guard case .sign(.doctor, let s2, let m2) = matcher.match(embedding: [0.3, 0.8, 0.3, -0.1], quality: good)
        else { return XCTFail("expected doctor") }
        XCTAssertEqual(s2, 0.955018, accuracy: 1e-6)
        XCTAssertEqual(m2, 0.143851, accuracy: 1e-6)

        XCTAssertEqual(matcher.match(embedding: [0.2, 0.2, 0.2, 0.2], quality: good), .unsure(.insufficientEvidence))
    }

    func testEachSignScoresItsBestReference() {
        // hello's far reference must not drag its score down or win for doctor
        let references: [(SignLabel, [Float])] = [(.hello, [-1, 0, 0]), (.hello, [1, 0, 0]), (.doctor, [0, 1, 0])]

        let result = SignMatcher(bundle(references)).match(embedding: [1, 0.1, 0], quality: good)

        guard case .sign(.hello, let similarity, _) = result else { return XCTFail("expected hello, got \(result)") }
        XCTAssertGreaterThan(similarity, 0.99)
    }

    func testRunnerUpIsTheNextSignNotTheSameSignsOtherReference() throws {
        // two near-identical hello references must not create a zero margin
        let references: [(SignLabel, [Float])] = [(.hello, [1, 0, 0]), (.hello, [1, 0.01, 0]), (.doctor, [0, 1, 0])]

        let result = SignMatcher(bundle(references)).match(embedding: [1, 0, 0], quality: good)

        guard case .sign(.hello, _, let margin) = result else { return XCTFail("expected hello, got \(result)") }
        XCTAssertEqual(margin, 1, accuracy: 1e-12)
    }

    func testEmbeddingsAreNormalizedBeforeComparing() {
        let references: [(SignLabel, [Float])] = [(.hello, [3, 0, 0]), (.doctor, [0, 0.5, 0])]

        let result = SignMatcher(bundle(references)).match(embedding: [250, 0, 0], quality: good)

        XCTAssertEqual(result, .sign(label: .hello, similarity: 1, margin: 1))
    }

    func testSimilarityIsClippedToOne() {
        // normalizing this vector and dotting it with itself gives 1.0000000000000002
        let vector: [Float] = [0.0828249454498291, 0.8782983422279358, -0.23759151995182037]
        let matcher = SignMatcher(bundle([(.hello, vector), (.doctor, [1, 0, 0])], similarity: 1, margin: 0))

        guard case .sign(.hello, let similarity, _) = matcher.match(embedding: vector, quality: good)
        else { return XCTFail("expected hello") }
        XCTAssertEqual(similarity, 1.0)
    }

    func testTiedSignsRankAlphabetically() {
        // query is equally close to both; "doctor" < "hello" whatever the bank order
        for references in [helloDoctor, helloDoctor.reversed()] {
            let matcher = SignMatcher(bundle(references, similarity: 0.5, margin: 0))

            guard case .sign(let label, _, let margin) = matcher.match(embedding: [1, 1, 0], quality: good)
            else { return XCTFail("expected a sign") }
            XCTAssertEqual(label, .doctor)
            XCTAssertEqual(margin, 0)
        }
    }

    // MARK: Similarity and margin cut-offs

    func testSimilarityExactlyAtTheCutOffIsAccepted() throws {
        let query: [Float] = [0.8, 0.6, 0]
        let (similarity, _) = try similarityAndMargin(query, helloDoctor)

        let atCutOff = SignMatcher(bundle(helloDoctor, similarity: similarity, margin: 0.05))
        XCTAssertEqual(atCutOff.match(embedding: query, quality: good).label, .hello)
    }

    func testSimilarityJustBelowTheCutOffIsUnsure() throws {
        let query: [Float] = [0.8, 0.6, 0]
        let (similarity, _) = try similarityAndMargin(query, helloDoctor)

        let aboveScore = SignMatcher(bundle(helloDoctor, similarity: similarity.nextUp, margin: 0.05))
        XCTAssertEqual(aboveScore.match(embedding: query, quality: good), .unsure(.insufficientEvidence))
    }

    func testMarginExactlyAtTheCutOffIsAccepted() throws {
        let query: [Float] = [0.8, 0.6, 0]
        let (_, margin) = try similarityAndMargin(query, helloDoctor)

        let atCutOff = SignMatcher(bundle(helloDoctor, similarity: 0.5, margin: margin))
        XCTAssertEqual(atCutOff.match(embedding: query, quality: good).label, .hello)
    }

    func testMarginJustBelowTheCutOffIsUnsure() throws {
        let query: [Float] = [0.8, 0.6, 0]
        let (_, margin) = try similarityAndMargin(query, helloDoctor)

        let aboveMargin = SignMatcher(bundle(helloDoctor, similarity: 0.5, margin: margin.nextUp))
        XCTAssertEqual(aboveMargin.match(embedding: query, quality: good), .unsure(.insufficientEvidence))
    }

    func testCloseRunnerUpIsUnsureEvenWithHighSimilarity() {
        let references: [(SignLabel, [Float])] = [(.hello, [1, 0, 0]), (.doctor, [0.99, 0.14, 0])]
        let matcher = SignMatcher(bundle(references, similarity: 0.8, margin: 0.05))

        XCTAssertEqual(matcher.match(embedding: [1, 0.07, 0], quality: good), .unsure(.insufficientEvidence))
    }

    // MARK: Tracking quality

    func testPoseFractionAtTheMinimumIsAcceptedAndBelowIsUnsure() {
        let matcher = SignMatcher(bundle(helloDoctor))

        XCTAssertEqual(matcher.match(embedding: [1, 0, 0], quality: .init(poseFraction: 0.6, handFraction: 1)).label, .hello)
        XCTAssertEqual(
            matcher.match(embedding: [1, 0, 0], quality: .init(poseFraction: 0.6.nextDown, handFraction: 1)),
            .unsure(.insufficientEvidence)
        )
    }

    func testHandFractionAtTheMinimumIsAcceptedAndBelowIsUnsure() {
        let matcher = SignMatcher(bundle(helloDoctor))

        XCTAssertEqual(matcher.match(embedding: [1, 0, 0], quality: .init(poseFraction: 1, handFraction: 0.2)).label, .hello)
        XCTAssertEqual(
            matcher.match(embedding: [1, 0, 0], quality: .init(poseFraction: 1, handFraction: 0.2.nextDown)),
            .unsure(.insufficientEvidence)
        )
    }

    func testQualityMinimumsComeFromTheBundle() {
        let strict = SignMatcher(bundle(helloDoctor, quality: .init(minPoseFraction: 0.9, minHandFraction: 0.5)))

        XCTAssertEqual(strict.match(embedding: [1, 0, 0], quality: .init(poseFraction: 0.85, handFraction: 1)), .unsure(.insufficientEvidence))
        XCTAssertEqual(strict.match(embedding: [1, 0, 0], quality: .init(poseFraction: 1, handFraction: 0.45)), .unsure(.insufficientEvidence))
        XCTAssertEqual(strict.match(embedding: [1, 0, 0], quality: .init(poseFraction: 0.9, handFraction: 0.5)).label, .hello)
    }

    // MARK: Invalid evidence

    func testNonFiniteEmbeddingIsUnsure() {
        let matcher = SignMatcher(bundle(helloDoctor))

        XCTAssertEqual(matcher.match(embedding: [.nan, 0, 0], quality: good), .unsure(.invalidEvidence))
        XCTAssertEqual(matcher.match(embedding: [1, .infinity, 0], quality: good), .unsure(.invalidEvidence))
    }

    func testZeroEmbeddingIsUnsure() {
        XCTAssertEqual(SignMatcher(bundle(helloDoctor)).match(embedding: [0, 0, 0], quality: good), .unsure(.invalidEvidence))
    }

    func testNonFiniteQualityIsUnsure() {
        let matcher = SignMatcher(bundle(helloDoctor))

        XCTAssertEqual(matcher.match(embedding: [1, 0, 0], quality: .init(poseFraction: .nan, handFraction: 1)), .unsure(.invalidEvidence))
        XCTAssertEqual(matcher.match(embedding: [1, 0, 0], quality: .init(poseFraction: 1, handFraction: .nan)), .unsure(.invalidEvidence))
        XCTAssertEqual(matcher.match(embedding: [1, 0, 0], quality: .init(poseFraction: .infinity, handFraction: 1)), .unsure(.invalidEvidence))
    }

    func testSingleLabelBankIsUnsureEvenForAnExactMatch() {
        let matcher = SignMatcher(bundle([(.hello, [1, 0, 0]), (.hello, [0, 1, 0])]))

        XCTAssertEqual(matcher.match(embedding: [1, 0, 0], quality: good), .unsure(.invalidEvidence))
    }

    func testEmptyBankIsUnsure() {
        XCTAssertEqual(SignMatcher(bundle([], dim: 3)).match(embedding: [1, 0, 0], quality: good), .unsure(.invalidEvidence))
    }

    func testUnusableReferenceMakesEveryMatchUnsure() {
        let matcher = SignMatcher(bundle(helloDoctor + [(.morning, [0, 0, 0])]))

        XCTAssertEqual(matcher.match(embedding: [1, 0, 0], quality: good), .unsure(.invalidEvidence))
    }

    func testNonFiniteCutOffsNeverAccept() {
        let matcher = SignMatcher(bundle(helloDoctor, similarity: .nan, margin: 0.05))

        XCTAssertEqual(matcher.match(embedding: [1, 0, 0], quality: good), .unsure(.invalidEvidence))
    }

    // MARK: Dimension mismatch

    func testQueryOfAnotherLengthIsADimensionMismatch() {
        let matcher = SignMatcher(bundle(helloDoctor))

        XCTAssertEqual(matcher.match(embedding: [1, 0], quality: good), .unsure(.dimensionMismatch))
        XCTAssertEqual(matcher.match(embedding: [1, 0, 0, 0], quality: good), .unsure(.dimensionMismatch))
        XCTAssertEqual(matcher.match(embedding: [.nan, 0], quality: good), .unsure(.dimensionMismatch))
    }

    func testQueryIsCheckedAgainstTheBundleDimensionNotOnlyTheReferences() {
        let matcher = SignMatcher(bundle([], dim: 3))

        XCTAssertEqual(matcher.match(embedding: [1, 0], quality: good), .unsure(.dimensionMismatch))
    }

    func testReferenceOfAnotherLengthIsADimensionMismatch() {
        let matcher = SignMatcher(bundle(helloDoctor + [(.morning, [0, 0, 1, 0])], dim: 3))

        XCTAssertEqual(matcher.match(embedding: [1, 0, 0], quality: good), .unsure(.dimensionMismatch))
    }
}

private extension MatchResult {
    var label: SignLabel? {
        if case .sign(let label, _, _) = self { label } else { nil }
    }
}
