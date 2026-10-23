import CallSession
import RecognitionCore
import SignPipeline
import XCTest
@testable import Ishara

final class SegmentClassifierTests: XCTestCase {
    private let clip = Landmarks.run(from: 0, seconds: 0.8, wristY: Landmarks.signingY)

    private func classifier(_ embedding: [Float], bundle: RecognitionBundle? = testBundle) -> (SegmentClassifier, FixedEmbeddingModel) {
        let model = FixedEmbeddingModel(embedding)
        return (SegmentClassifier(encoder: SignEncoder(model: model), matcher: bundle.map(SignMatcher.init)), model)
    }

    func testCloseMatchBecomesTheSign() {
        let (classifier, model) = classifier([0.99, 0.05, 0, 0])

        XCTAssertEqual(classifier.classify(clip), .sign(.hello))
        XCTAssertEqual(model.calls, 1)
    }

    func testLowConfidenceIsUnsure() {
        let (classifier, _) = classifier([0.7, 0.7, 0, 0])

        XCTAssertEqual(classifier.classify(clip), .unsure)
    }

    func testWithoutABundleEverySignIsUnsure() {
        let (classifier, model) = classifier([1, 0, 0, 0], bundle: nil)

        XCTAssertEqual(classifier.classify(clip), .unsure)
        XCTAssertEqual(model.calls, 0, "nothing to match against, so nothing is encoded")
    }

    func testWithoutAnEncoderEverySignIsUnsure() {
        let classifier = SegmentClassifier(encoder: nil, matcher: SignMatcher(testBundle))

        XCTAssertEqual(classifier.classify(clip), .unsure)
    }

    func testEncoderFailureIsUnsure() {
        let (classifier, model) = classifier([1, 0, 0, 0])
        model.shouldFail = true

        XCTAssertEqual(classifier.classify(clip), .unsure)
    }

    func testClipTooShortToEncodeIsUnsure() {
        let (classifier, _) = classifier([1, 0, 0, 0])

        XCTAssertEqual(classifier.classify(Array(clip.prefix(3))), .unsure)
    }

    func testPoorlyTrackedClipIsUnsureEvenWhenTheEmbeddingMatches() {
        let (classifier, _) = classifier([1, 0, 0, 0])
        let handless = (0..<24).map { Landmarks.frame(t: Double($0) / 30, hands: false) }

        XCTAssertEqual(classifier.classify(handless), .unsure)
    }

    func testQualityCountsBodyAndHandsPerFrame() {
        let frames = [Landmarks.frame(t: 0), Landmarks.frame(t: 0.1, body: false, hands: false)]

        let quality = SegmentClassifier.quality(of: frames)

        XCTAssertEqual(quality.poseFraction, 0.5, accuracy: 1e-9)
        XCTAssertEqual(quality.handFraction, 0.5, accuracy: 1e-9)
    }

    func testEveryBundleLabelIsASignTheBackendKnows() {
        XCTAssertEqual(SignLabel.allCases.map(\.rawValue), Sign.allCases.map(\.rawValue))
    }
}
