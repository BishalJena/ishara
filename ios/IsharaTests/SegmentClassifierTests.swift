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

    // MARK: ASL Signs model (D8)

    /// The bundle the app ships (Resources/asl-bundle.json).
    private var aslBundle: LogitsBundle {
        RecognitionAssets.loadLogitsBundle(from: Bundle.main.url(forResource: "asl-bundle", withExtension: "json"))!
    }

    /// Logits with `gloss` at probability ≈ `p` and the rest spread evenly.
    private func logits(_ gloss: String, p: Double) -> [Float] {
        let glosses = aslBundle.glosses
        let rest = (1 - p) / Double(glosses.count - 1)
        return glosses.map { Float(log($0 == gloss ? p : rest)) }
    }

    private func asl(_ logits: [Float]) -> (SegmentClassifier, FixedLogitsModel) {
        let model = FixedLogitsModel(logits)
        return (SegmentClassifier(logitsModel: model, matcher: LogitsMatcher(aslBundle)), model)
    }

    func testConfidentVocabularySignIsAChip() {
        let (classifier, model) = asl(logits("tomorrow", p: 0.8))

        XCTAssertEqual(classifier.classify(clip), .sign(.tomorrow))
        XCTAssertEqual(model.frameCounts, [clip.count])
        XCTAssertEqual(model.lastValueCount, clip.count * KaggleLayout.valuesPerFrame, "Kaggle 543 × 3 per frame")
    }

    func testGreyZoneVocabularySignIsACandidate() {
        let (classifier, _) = asl(logits("tomorrow", p: 0.4))

        XCTAssertEqual(classifier.classify(clip), .candidate(.tomorrow))
    }

    func testConfidentUnrehearsedSignIsUnsure() {
        // In the backend's vocabulary but not rehearsed: public YES clips read as can (Gate 2).
        for gloss in ["can", "morning"] {
            let (classifier, _) = asl(logits(gloss, p: 0.9))

            XCTAssertEqual(classifier.classify(clip), .unsure, gloss)
        }
    }

    func testConfidentWordOutsideTheVocabularyIsUnsure() {
        // The open-set rule: "mitten" at 0.98 is not turned into the best vocabulary word.
        let (classifier, _) = asl(logits("mitten", p: 0.98))

        XCTAssertEqual(classifier.classify(clip), .unsure)
    }

    func testModelFailureIsUnsure() {
        let (classifier, model) = asl(logits("tomorrow", p: 0.9))
        model.shouldFail = true

        XCTAssertEqual(classifier.classify(clip), .unsure)
    }

    func testUnsureSignWithAHandOffTheSideSaysSo() {
        let (classifier, _) = asl(logits("mitten", p: 0.98))

        XCTAssertEqual(classifier.classify(rightHandLeavesMidSign), .handLeftFrame)
    }

    func testAConfidentSignFromAPartialViewIsNotAChip() {
        let (classifier, _) = asl(logits("tomorrow", p: 0.9))

        XCTAssertEqual(classifier.classify(rightHandLeavesMidSign), .handLeftFrame)
    }

    func testAPartialViewIsNotADidYouMeanTileEither() {
        let (classifier, _) = asl(logits("tomorrow", p: 0.4))

        XCTAssertEqual(classifier.classify(rightHandLeavesMidSign), .handLeftFrame)
    }

    // MARK: Issue #58: a one-handed sign whose hand leaves the picture

    func testAOneHandedSignWhoseHandLeavesTheSideShowsTheFramingHint() {
        // The detector counts the vanished hand as rest and ends the sign at once, so the cut
        // itself has the hand in view; only the rest frames after it show where it went.
        let (classifier, _) = asl(logits("tomorrow", p: 0.9))

        let clips = cutBySession(Landmarks.oneHandedSign(wristAfter: (x: -0.4, y: 0.6)))

        XCTAssertEqual(clips.map(classifier.classify), [.handLeftFrame])
    }

    func testAOneHandedSignThatEndsAtRestKeepsItsChip() {
        let (classifier, model) = asl(logits("tomorrow", p: 0.9))

        let clips = cutBySession(Landmarks.oneHandedSign(wristAfter: (x: 0.4, y: 1.2)))

        XCTAssertEqual(clips.map(classifier.classify), [.sign(.tomorrow)])
        XCTAssertEqual(model.frameCounts, clips.map(\.frames.count), "the model never reads the rest after the cut")
    }

    func testAnArmRestingPastTheSideEdgeInPortraitIsNoFramingHint() {
        // 9:16 crops (issue #58): the dropped hand's pose wrist sits past the edge, below the rest line.
        let (classifier, _) = asl(logits("tomorrow", p: 0.9))

        let clips = cutBySession(Landmarks.oneHandedSign(wristAfter: (x: -0.1, y: 0.95)))

        XCTAssertEqual(clips.map(classifier.classify), [.sign(.tomorrow)])
    }

    /// Right hand (pose wrist 16) leaves past the right edge for the second half of the clip.
    private var rightHandLeavesMidSign: [LandmarkFrame] {
        (0..<30).map { index -> LandmarkFrame in
            let inside = index < 12
            var frame = Landmarks.frame(t: Double(index) / 30, wristY: Landmarks.signingY, rightHand: inside)
            if !inside { frame.pose?[16] = Landmark(x: 1.1, y: 0.45, z: 0, visibility: 0.2) }
            return frame
        }
    }

    /// The accepted signs `RecognitionSession` cuts from a calibrated stream.
    private func cutBySession(_ sign: (Double) -> [LandmarkFrame]) -> [RecognitionSession.SignClip] {
        var session = RecognitionSession()
        return Landmarks.calibratedStream(then: sign).flatMap { session.process($0) }.compactMap { output in
            if case .segment(let clip) = output { clip } else { nil }
        }
    }

    func testTheShippedBundleMatchesTheMacOne() throws {
        // The Mac bridge's bundle (spikes/recognition/fixtures/asl), read from the source tree.
        let mac = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().appendingPathComponent("spikes/recognition/fixtures/asl/asl-bundle-provisional.json")
        let macBundle = try LogitsBundle.load(from: Data(contentsOf: mac))

        XCTAssertEqual(aslBundle, macBundle, "vocabulary and thresholds must match the Mac bridge")
        XCTAssertEqual(aslBundle.model.sha256, "f55a2bb1ebe6d1e912a98e31c6ef3f995c9ae261f408fe115f2008099d3f0bb7")
        XCTAssertTrue(Set(aslBundle.vocabulary).isSubset(of: Set(Sign.allCases.map(\.rawValue))))
    }
}

/// Returns the same logits for every clip and records what it was given.
final class FixedLogitsModel: LogitsModel {
    let values: [Float]
    var shouldFail = false
    private(set) var frameCounts: [Int] = []
    private(set) var lastValueCount = 0

    init(_ values: [Float]) { self.values = values }

    func logits(landmarks: [Float], frameCount: Int) throws -> [Float] {
        frameCounts.append(frameCount)
        lastValueCount = landmarks.count
        if shouldFail { throw SignEncoderError.zeroEmbedding }
        return values
    }
}

private extension SegmentClassifier {
    /// A cut sign at the rest line calibration gives for the scripted landmarks.
    func classify(_ frames: [LandmarkFrame]) -> RecognitionResult {
        classify(RecognitionSession.SignClip(frames: frames, restAfter: [], restY: Landmarks.calibratedRestY))
    }
}
