import Foundation
import SignPipeline
import XCTest
@testable import Ishara

/// PLAN P3 as far as a simulator can take it: runs saved clips through the app's own path
/// (Holistic Landmarker task → Kaggle layout → LiteRT model, from the app bundle's LocalAssets)
/// and writes what it saw, so spikes/asl_probe/parity.py can compare it with the Mac path
/// (legacy Holistic → the same model) on the same clips. Skips unless both paths are set:
///
///     TEST_RUNNER_ISHARA_PARITY_CLIPS=<dir of .mp4/.mov> TEST_RUNNER_ISHARA_PARITY_OUT=<dir> \
///       xcodebuild test ... -only-testing:IsharaTests/ASLParityHarness
///
/// Per clip it writes `<stem>.f32` (the Kaggle values, float32 little-endian, frames × 543 × 3)
/// and one `simulator.json` with the logits and tracking fractions.
final class ASLParityHarness: XCTestCase {
    struct ClipResult: Encodable {
        let clip: String
        let frames: Int
        let skippedFrames: Int
        let leftHandFraction: Double
        let rightHandFraction: Double
        let poseFraction: Double
        let logits: [Float]
        let seconds: Double
    }

    func testWritesTheAppPathsOutputForSavedClips() async throws {
        let environment = ProcessInfo.processInfo.environment
        guard let input = environment["ISHARA_PARITY_CLIPS"], let output = environment["ISHARA_PARITY_OUT"] else {
            throw XCTSkip("set TEST_RUNNER_ISHARA_PARITY_CLIPS and TEST_RUNNER_ISHARA_PARITY_OUT to run")
        }
        let assets = RecognitionAssets.inMainBundle()
        let modelURL = try XCTUnwrap(assets.aslModel, "asl-signs.tflite is missing from LocalAssets")
        let model = try RecognitionAssets.makeLogitsModel(modelURL)
        let outputURL = URL(fileURLWithPath: output, isDirectory: true)
        try FileManager.default.createDirectory(at: outputURL, withIntermediateDirectories: true)
        let clips = try FileManager.default.contentsOfDirectory(
            at: URL(fileURLWithPath: input, isDirectory: true), includingPropertiesForKeys: nil)
            .filter { ["mp4", "mov", "m4v"].contains($0.pathExtension.lowercased()) }
            .sorted { $0.lastPathComponent < $1.lastPathComponent }
        XCTAssertFalse(clips.isEmpty, "no clips in \(input)")

        var results: [ClipResult] = []
        for clip in clips {
            let start = Date()
            // A fresh landmarker per clip: video mode needs increasing timestamps.
            let provider = try assets.makeLandmarkProvider()
            var frames: [LandmarkFrame] = []
            var skipped = 0
            for try await frame in VideoFileFrameSource(url: clip).frames() {
                do {
                    frames.append(try provider.landmarks(for: frame))
                } catch {
                    skipped += 1
                }
            }
            guard !frames.isEmpty else { continue }
            let values = KaggleLayout.values(for: frames)
            let logits = try model.logits(landmarks: values, frameCount: frames.count)
            let stem = clip.deletingPathExtension().lastPathComponent
            try values.withUnsafeBytes { Data($0) }.write(to: outputURL.appendingPathComponent("\(stem).f32"))
            let count = Double(frames.count)
            results.append(ClipResult(
                clip: clip.lastPathComponent, frames: frames.count, skippedFrames: skipped,
                leftHandFraction: Double(frames.count { $0.leftHand != nil }) / count,
                rightHandFraction: Double(frames.count { $0.rightHand != nil }) / count,
                poseFraction: Double(frames.count { $0.pose != nil }) / count,
                logits: logits, seconds: Date().timeIntervalSince(start)))
        }
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        try encoder.encode(results).write(to: outputURL.appendingPathComponent("simulator.json"))
        XCTAssertEqual(results.count, clips.count, "every clip produced landmarks")
    }
}
