import CallSession
import Foundation
import OSLog
import RecognitionCore
import SignPipeline

/// Turns the landmark frames of one accepted sign into a chip: SignCLIP features → Core ML
/// embedding → nearest enrolled reference. Never guesses: without an encoder or a
/// recognition bundle, or when any step fails, the result is `.unsure` (a [?] chip).
struct SegmentClassifier {
    let encoder: SignEncoder?
    let matcher: SignMatcher?

    func classify(_ frames: [LandmarkFrame]) -> RecognitionResult {
        guard let encoder, let matcher else { return .unsure }
        var clip = ClipBuffer()
        frames.forEach { clip.append($0) }
        let embedding: SignEmbedding
        do {
            embedding = try encoder.embed(clip)
        } catch {
            // Too short, too long, no shoulders or a bad model output: not a sign we can judge.
            recognitionLog.info("clip not encoded: \(String(describing: error), privacy: .public)")
            return .unsure
        }
        switch matcher.match(embedding: embedding.values, quality: Self.quality(of: frames)) {
        case .sign(let label, _, _):
            return Sign(rawValue: label.rawValue).map(RecognitionResult.sign) ?? .unsure
        case .unsure(let reason):
            recognitionLog.info("unsure: \(reason.rawValue, privacy: .public)")
            return .unsure
        }
    }

    static func quality(of frames: [LandmarkFrame]) -> ClipQuality {
        ClipQuality.from(frames: frames.map { frame in
            ClipQuality.Frame(
                body: frame.hasTrackedShoulders,
                handCount: [frame.leftHand, frame.rightHand].compactMap { $0 }.count
            )
        })
    }
}
