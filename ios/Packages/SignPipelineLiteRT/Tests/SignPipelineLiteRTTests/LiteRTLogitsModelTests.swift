import Foundation
import SignPipeline
import SignPipelineLiteRT
import XCTest

/// The fixture holds the Mac's LiteRT logits (ai-edge-litert, the runtime behind the Mac
/// bridge and every number in docs/experiments/asl-model-probe.md) for a deterministic input.
/// Regenerate it from the repository root with the asl_signs venv:
///
///     T = 24; t, p, c = np.meshgrid(np.arange(T), np.arange(543), np.arange(3), indexing="ij")
///     x = (0.5 + 0.3 * np.sin(0.37 * t + 0.011 * p + 0.5 * c)).astype(np.float32)
///     x[0::2, 468:489] = np.nan; x[5, 0:468] = np.nan
///     Interpreter(model_path=...).get_signature_runner("serving_default")(inputs=x)["outputs"]
final class LiteRTLogitsModelTests: XCTestCase {
    struct Fixture: Decodable {
        let frames: Int
        let logits: [Float]
        let top5: [Int]
    }

    func testRejectsInputThatIsNotWholeFrames() {
        XCTAssertThrowsError(try LiteRTLogitsModel.checkInput(landmarks: [0, 1], frameCount: 1)) {
            XCTAssertEqual($0 as? LiteRTLogitsModelError, .badInput(values: 2, frames: 1))
        }
        XCTAssertThrowsError(try LiteRTLogitsModel.checkInput(landmarks: [], frameCount: 0))
        XCTAssertNoThrow(try LiteRTLogitsModel.checkInput(
            landmarks: [Float](repeating: 0, count: 2 * KaggleLayout.valuesPerFrame), frameCount: 2))
    }

    #if os(iOS)
    func testMatchesTheMacRuntimeOnTheFixture() throws {
        let fixture = try loadFixture()
        let model = try LiteRTLogitsModel(contentsOf: try modelURL())
        XCTAssertEqual(model.classCount, 250)

        let logits = try model.logits(landmarks: Self.input(frames: fixture.frames), frameCount: fixture.frames)

        XCTAssertEqual(logits.count, fixture.logits.count)
        let worst = zip(logits, fixture.logits).map { abs($0 - $1) }.max() ?? .infinity
        XCTAssertLessThan(worst, 1e-3, "largest logit difference from the Mac runtime")
        let top5 = logits.indices.sorted { logits[$0] > logits[$1] }.prefix(5)
        XCTAssertEqual(Array(top5), fixture.top5)
    }

    func testResizesForEachClipLength() throws {
        let model = try LiteRTLogitsModel(contentsOf: try modelURL())
        for frames in [8, 40, 8, 1] {
            let logits = try model.logits(landmarks: Self.input(frames: frames), frameCount: frames)
            XCTAssertEqual(logits.count, 250, "\(frames) frames")
        }
    }

    func testRunsWellInsideTheLiveBudget() throws {
        let model = try LiteRTLogitsModel(contentsOf: try modelURL())
        let input = Self.input(frames: 45)
        _ = try model.logits(landmarks: input, frameCount: 45)
        let start = Date()
        for _ in 0..<10 { _ = try model.logits(landmarks: input, frameCount: 45) }
        let perClip = Date().timeIntervalSince(start) / 10
        XCTAssertLessThan(perClip, 0.1, "seconds per 1.5 s clip")
    }
    #endif

    // MARK: - Helpers

    static func input(frames: Int) -> [Float] {
        var values = [Float](repeating: 0, count: frames * KaggleLayout.valuesPerFrame)
        for t in 0..<frames {
            for p in 0..<KaggleLayout.points {
                for c in 0..<3 {
                    let phase = 0.37 * Double(t) + 0.011 * Double(p) + 0.5 * Double(c)
                    var value = Float(0.5 + 0.3 * sin(phase))
                    if t % 2 == 0, (468..<489).contains(p) { value = .nan }
                    if t == 5, p < 468 { value = .nan }
                    values[(t * KaggleLayout.points + p) * 3 + c] = value
                }
            }
        }
        return values
    }

    private func loadFixture() throws -> Fixture {
        let url = try XCTUnwrap(Bundle.module.url(forResource: "runtime_parity", withExtension: "json", subdirectory: "Fixtures"))
        return try JSONDecoder().decode(Fixture.self, from: Data(contentsOf: url))
    }

    /// ios/Ishara/LocalAssets/asl-signs.tflite, from Scripts/download_asl_model.sh.
    private func modelURL() throws -> URL {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Ishara/LocalAssets/asl-signs.tflite")
        try XCTSkipUnless(
            FileManager.default.fileExists(atPath: url.path),
            "asl-signs.tflite is missing; run Scripts/download_asl_model.sh ios/Ishara/LocalAssets"
        )
        return url
    }
}
