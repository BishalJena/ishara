import CallSession
import Foundation
import OSLog
import RecognitionCore
import SignPipeline

/// Turns the landmark frames of one accepted sign into a chip, a "did you mean" candidate or
/// `?`. Two engines:
/// - `asl` (decision D8): Kaggle-layout landmarks → the public ASL Signs model → 250 logits →
///   the open-set rule in `LogitsMatcher` (chip, pick-one, or `?`).
/// - `signCLIP`: SignCLIP features → Core ML embedding → nearest enrolled reference.
/// Never guesses: without a model or bundle, or when any step fails, the result is `.unsure`;
/// when a hand left the picture during the sign or as it ended, it is `.handLeftFrame`.
struct SegmentClassifier {
    enum Engine {
        case signCLIP(encoder: SignEncoder?, matcher: SignMatcher?)
        case asl(model: any LogitsModel, matcher: LogitsMatcher)
    }

    let engine: Engine

    init(encoder: SignEncoder?, matcher: SignMatcher?) {
        engine = .signCLIP(encoder: encoder, matcher: matcher)
    }

    init(logitsModel: any LogitsModel, matcher: LogitsMatcher) {
        engine = .asl(model: logitsModel, matcher: matcher)
    }

    func classify(_ clip: RecognitionSession.SignClip) -> RecognitionResult {
        let frames = clip.frames
        let result: RecognitionResult
        switch engine {
        case let .signCLIP(encoder, matcher):
            result = Self.classify(frames, encoder: encoder, matcher: matcher)
        case let .asl(model, matcher):
            result = Self.classify(frames, model: model, matcher: matcher)
        }
        // The rest after the cut counts too: a hand that leaves the picture ends the sign there.
        // A sign read while a hand was out of the picture is never a chip or a tile.
        guard FramingGuard.handLeftFrame(Self.framing(of: frames + clip.restAfter), restY: clip.restY) else {
            return result
        }
        recognitionLog.info("hand left the picture: \(String(describing: result), privacy: .public) shown as ?")
        return .handLeftFrame
    }

    private static func classify(_ frames: [LandmarkFrame], encoder: SignEncoder?, matcher: SignMatcher?) -> RecognitionResult {
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
        switch matcher.match(embedding: embedding.values, quality: quality(of: frames)) {
        case .sign(let label, _, _):
            return Sign(rawValue: label.rawValue).map(RecognitionResult.sign) ?? .unsure
        case .unsure(let reason):
            recognitionLog.info("unsure: \(reason.rawValue, privacy: .public)")
            return .unsure
        }
    }

    private static func classify(_ frames: [LandmarkFrame], model: any LogitsModel, matcher: LogitsMatcher) -> RecognitionResult {
        guard !frames.isEmpty else { return .unsure }
        let logits: [Float]
        do {
            logits = try model.logits(landmarks: KaggleLayout.values(for: frames), frameCount: frames.count)
        } catch {
            recognitionLog.info("model failed: \(String(describing: error), privacy: .public)")
            return .unsure
        }
        let result = matcher.match(logits: logits, quality: quality(of: frames))
        switch result {
        case let .chip(label, p, _, top):
            log("chip", label.rawValue, p, top, frames.count)
            return Sign(rawValue: label.rawValue).map(RecognitionResult.sign) ?? .unsure
        case let .pickOne(label, p, _, top):
            log("pick one", label.rawValue, p, top, frames.count)
            return Sign(rawValue: label.rawValue).map(RecognitionResult.candidate) ?? .unsure
        case let .unsure(reason, top):
            log("unsure", reason, top.first?.p ?? 0, top, frames.count)
            return .unsure
        }
    }

    private static func log(_ verdict: String, _ detail: String, _ p: Double, _ top: [LogitsCandidate], _ frames: Int) {
        let ranked = top.map { "\($0.gloss) \(String(format: "%.2f", $0.p))" }.joined(separator: ", ")
        recognitionLog.info("asl \(verdict, privacy: .public): \(detail, privacy: .public) p=\(p, privacy: .public) [\(ranked, privacy: .public)] frames=\(frames, privacy: .public)")
    }

    static func quality(of frames: [LandmarkFrame]) -> ClipQuality {
        ClipQuality.from(frames: frames.map { frame in
            ClipQuality.Frame(
                body: frame.hasTrackedShoulders,
                handCount: [frame.leftHand, frame.rightHand].compactMap { $0 }.count
            )
        })
    }

    /// MediaPipe pose wrists: 15 is the left wrist, 16 the right, matching the Holistic hands.
    static func framing(of frames: [LandmarkFrame]) -> [FramingGuard.Frame] {
        frames.map { frame in
            func hand(_ landmarks: [Landmark]?, wrist index: Int) -> FramingGuard.Hand {
                let wrist = frame.pose?[index]
                return FramingGuard.Hand(tracked: landmarks != nil, wristX: wrist?.x, wristY: wrist?.y)
            }
            return FramingGuard.Frame(
                timestamp: frame.timestamp,
                left: hand(frame.leftHand, wrist: 15),
                right: hand(frame.rightHand, wrist: 16)
            )
        }
    }
}
