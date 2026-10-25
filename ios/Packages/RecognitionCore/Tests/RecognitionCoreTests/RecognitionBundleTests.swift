import Foundation
import RecognitionCore
import XCTest

final class RecognitionBundleTests: XCTestCase {
    /// A valid exported bundle as JSON; tests change one field at a time.
    private func bundleJSON(
        version: Any = 1,
        embeddingDim: Any = 3,
        similarity: Any = 0.8,
        margin: Any = 0.05,
        minPose: Any = 0.6,
        references: [[String: Any]]? = nil
    ) -> [String: Any] {
        [
            "version": version,
            "encoder": "signclip-test",
            "embedding_dim": embeddingDim,
            "thresholds": ["similarity": similarity, "margin": margin],
            "quality": ["min_pose_fraction": minPose, "min_hand_fraction": 0.2],
            "references": references ?? [
                ["id": "hello-1", "label": "hello", "embedding": [1, 0, 0]],
                ["id": "hello-2", "label": "hello", "embedding": [0.9, 0.1, 0]],
                ["id": "doctor-1", "label": "doctor", "embedding": [0, 1, 0]],
            ],
        ]
    }

    private func load(_ object: [String: Any]) throws -> RecognitionBundle {
        try RecognitionBundle.load(from: JSONSerialization.data(withJSONObject: object))
    }

    private func assertLoadFails(
        _ object: [String: Any],
        with expected: BundleValidationError,
        file: StaticString = #filePath,
        line: UInt = #line
    ) {
        XCTAssertThrowsError(try load(object), file: file, line: line) {
            XCTAssertEqual($0 as? BundleValidationError, expected, file: file, line: line)
        }
    }

    private func validBundle() throws -> RecognitionBundle { try load(bundleJSON()) }

    private func assertInvalid(
        _ bundle: RecognitionBundle,
        _ expected: BundleValidationError,
        file: StaticString = #filePath,
        line: UInt = #line
    ) {
        XCTAssertThrowsError(try bundle.validate(), file: file, line: line) {
            XCTAssertEqual($0 as? BundleValidationError, expected, file: file, line: line)
        }
    }

    // MARK: Loading

    func testValidBundleLoadsEveryField() throws {
        let bundle = try validBundle()

        XCTAssertEqual(bundle.version, 1)
        XCTAssertEqual(bundle.encoder, "signclip-test")
        XCTAssertEqual(bundle.embeddingDim, 3)
        XCTAssertEqual(bundle.thresholds, .init(similarity: 0.8, margin: 0.05))
        XCTAssertEqual(bundle.quality, .init(minPoseFraction: 0.6, minHandFraction: 0.2))
        XCTAssertEqual(bundle.references.map(\.id), ["hello-1", "hello-2", "doctor-1"])
        XCTAssertEqual(bundle.references.map(\.label), [.hello, .hello, .doctor])
        XCTAssertEqual(bundle.references[1].embedding, [0.9, 0.1, 0])
    }

    func testEncodingRoundTripsWithSnakeCaseKeys() throws {
        let bundle = try validBundle()
        let data = try JSONEncoder().encode(bundle)
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])

        XCTAssertEqual(object["embedding_dim"] as? Int, 3)
        XCTAssertNotNil((object["quality"] as? [String: Any])?["min_pose_fraction"])
        XCTAssertEqual(try RecognitionBundle.load(from: data), bundle)
    }

    func testEveryVocabularyLabelIsAccepted() throws {
        let references = SignLabel.allCases.enumerated().map { index, label in
            ["id": "r\(index)", "label": label.rawValue, "embedding": [1, Double(index), 0]] as [String: Any]
        }

        XCTAssertEqual(Set(try load(bundleJSON(references: references)).references.map(\.label)), Set(SignLabel.allCases))
        XCTAssertEqual(SignLabel.allCases.count, 34)  // 12 template signs + 22 ASL glosses (D8)
    }

    // MARK: Validation failures

    func testOtherVersionsAreRejected() {
        assertLoadFails(bundleJSON(version: 2), with: .unsupportedVersion(2))
        assertLoadFails(bundleJSON(version: 0), with: .unsupportedVersion(0))
    }

    func testOtherVersionIsReportedEvenWhenItsFieldsDiffer() {
        assertLoadFails(["version": 2, "model": "something-else"], with: .unsupportedVersion(2))
    }

    func testLabelOutsideTheVocabularyIsRejected() {
        let references: [[String: Any]] = [
            ["id": "a", "label": "hello", "embedding": [1, 0, 0]],
            ["id": "b", "label": "hospital", "embedding": [0, 1, 0]],
        ]

        assertLoadFails(bundleJSON(references: references), with: .unknownLabel("hospital"))
    }

    func testLabelsAreCaseSensitive() {
        let references: [[String: Any]] = [
            ["id": "a", "label": "Hello", "embedding": [1, 0, 0]],
            ["id": "b", "label": "doctor", "embedding": [0, 1, 0]],
        ]

        assertLoadFails(bundleJSON(references: references), with: .unknownLabel("Hello"))
    }

    func testEmbeddingOfTheWrongLengthIsRejected() {
        let references: [[String: Any]] = [
            ["id": "a", "label": "hello", "embedding": [1, 0, 0]],
            ["id": "b", "label": "doctor", "embedding": [0, 1]],
        ]

        assertLoadFails(bundleJSON(references: references), with: .embeddingDimensionMismatch(referenceID: "b", expected: 3, actual: 2))
    }

    func testNonPositiveEmbeddingDimensionIsRejected() {
        assertLoadFails(bundleJSON(embeddingDim: 0, references: []), with: .invalidEmbeddingDimension(0))
    }

    func testAllZeroEmbeddingIsRejected() {
        let references: [[String: Any]] = [
            ["id": "a", "label": "hello", "embedding": [1, 0, 0]],
            ["id": "z", "label": "doctor", "embedding": [0, 0, 0]],
        ]

        assertLoadFails(bundleJSON(references: references), with: .zeroNormEmbedding(referenceID: "z"))
    }

    func testNonFiniteEmbeddingIsRejected() throws {
        var bundle = try validBundle()
        bundle.references[2].embedding = [0, .nan, 0]
        assertInvalid(bundle, .nonFiniteEmbedding(referenceID: "doctor-1"))

        bundle.references[2].embedding = [0, .infinity, 0]
        assertInvalid(bundle, .nonFiniteEmbedding(referenceID: "doctor-1"))
    }

    func testSingleLabelBankIsRejected() {
        let references: [[String: Any]] = [
            ["id": "a", "label": "hello", "embedding": [1, 0, 0]],
            ["id": "b", "label": "hello", "embedding": [0, 1, 0]],
        ]

        assertLoadFails(bundleJSON(references: references), with: .tooFewLabels(1))
    }

    func testEmptyBankIsRejected() {
        assertLoadFails(bundleJSON(references: []), with: .tooFewLabels(0))
    }

    func testNonFiniteThresholdsAreRejected() throws {
        var bundle = try validBundle()
        bundle.thresholds.similarity = .nan
        assertInvalid(bundle, .nonFiniteThresholds)

        bundle = try validBundle()
        bundle.thresholds.margin = .infinity
        assertInvalid(bundle, .nonFiniteThresholds)
    }

    func testQualityRequirementsMustBeFractions() throws {
        assertLoadFails(bundleJSON(minPose: 1.5), with: .invalidQualityRequirements)

        var bundle = try validBundle()
        bundle.quality.minHandFraction = -0.1
        assertInvalid(bundle, .invalidQualityRequirements)
        bundle.quality.minHandFraction = .nan
        assertInvalid(bundle, .invalidQualityRequirements)
        bundle.quality.minHandFraction = 1
        XCTAssertNoThrow(try bundle.validate())
    }

    func testProvisionalTryBundleIsRefused() throws {
        var object = bundleJSON()
        object["provisional"] = true
        assertLoadFails(object, with: .provisional)

        object["provisional"] = false
        XCTAssertEqual(try load(object), try validBundle())
    }

    func testMissingFieldFailsToDecode() {
        var object = bundleJSON()
        object.removeValue(forKey: "thresholds")

        XCTAssertThrowsError(try load(object)) { XCTAssertTrue($0 is DecodingError) }
    }
}
