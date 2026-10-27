import Foundation
import RecognitionCore
import SignPipeline
#if canImport(SignPipelineMediaPipe)
import SignPipelineMediaPipe
#endif
#if canImport(SignPipelineLiteRT)
import SignPipelineLiteRT
#endif

/// Model and data files the recognition pipeline loads from the app bundle. Models and
/// recordings are large or personal, so they're not in Git: put them in
/// `ios/Ishara/LocalAssets/` (see the README there) and Xcode copies that folder into the app.
///
/// With `asl-signs.tflite` installed the ASL Signs model runs (decision D8), with the open-set
/// thresholds from `asl-bundle.json` (committed, in Resources). Otherwise the older SignCLIP
/// path runs if its encoder and bundle are installed.
struct RecognitionAssets: Sendable {
    static let folder = "LocalAssets"

    var holisticModel: URL?
    /// `SignCLIPEncoder.mlmodelc` (or an `.mlpackage`, compiled on first launch).
    var encoderModel: URL?
    var recognitionBundle: URL?
    /// The public ASL Signs 1st-place model (D8).
    var aslModel: URL?
    /// Its version-2 logits bundle: glosses, vocabulary and thresholds.
    var aslBundle: URL?
    /// `SampleSigns/*.mov|mp4|m4v`, replayed in the simulator.
    var sampleClips: [URL]

    static func inMainBundle() -> RecognitionAssets {
        let bundle = Bundle.main
        func find(_ name: String, _ extensions: [String]) -> URL? {
            extensions.lazy.compactMap { bundle.url(forResource: name, withExtension: $0, subdirectory: folder) }.first
        }
        let clips = ["mov", "mp4", "m4v"].flatMap {
            bundle.urls(forResourcesWithExtension: $0, subdirectory: "\(folder)/SampleSigns") ?? []
        }
        return RecognitionAssets(
            holisticModel: find("holistic_landmarker", ["task"]),
            encoderModel: find("SignCLIPEncoder", ["mlmodelc", "mlpackage"]),
            recognitionBundle: find("recognition-bundle", ["json"]),
            aslModel: find("asl-signs", ["tflite"]),
            aslBundle: bundle.url(forResource: "asl-bundle", withExtension: "json"),
            sampleClips: clips
        )
    }

    /// The ASL model runs when it is installed (D8); SignCLIP is the fallback.
    var usesASLModel: Bool { aslModel != nil }

    /// Shown on Get ready when recognition will run but can only answer [?], or when its
    /// thresholds are still provisional (never hidden, as on the Mac bridge).
    var notice: String? {
        if usesASLModel {
            guard let bundle = Self.loadLogitsBundle(from: aslBundle) else {
                return "The ASL recognition bundle is missing or invalid, so every sign will show [?]."
            }
            return bundle.provisional
                ? "ASL recognition thresholds are provisional: not yet frozen on a labelled phone session."
                : nil
        }
        if recognitionBundle == nil {
            return "No recognition bundle installed, so every sign will show [?]."
        }
        if encoderModel == nil {
            return "No SignCLIP encoder installed, so every sign will show [?]."
        }
        return nil
    }

    /// Builds the landmark provider and the classifier. Runs on the worker thread.
    /// A missing or broken model or bundle leaves the classifier answering `.unsure`.
    func makeComponents() throws -> PipelineComponents {
        PipelineComponents(landmarks: try makeLandmarkProvider(), classifier: makeClassifier())
    }

    func makeClassifier() -> SegmentClassifier {
        if let aslModel {
            guard let bundle = Self.loadLogitsBundle(from: aslBundle) else {
                return SegmentClassifier(encoder: nil, matcher: nil)
            }
            do {
                return SegmentClassifier(logitsModel: try Self.makeLogitsModel(aslModel), matcher: LogitsMatcher(bundle))
            } catch {
                recognitionLog.error("ASL model not loaded: \(String(describing: error), privacy: .public)")
                return SegmentClassifier(encoder: nil, matcher: nil)
            }
        }
        var encoder: SignEncoder?
        if let encoderModel {
            do {
                encoder = SignEncoder(model: try CoreMLEmbeddingModel(contentsOf: encoderModel))
            } catch {
                recognitionLog.error("encoder not loaded: \(String(describing: error), privacy: .public)")
            }
        }
        return SegmentClassifier(encoder: encoder, matcher: Self.loadMatcher(from: recognitionBundle))
    }

    /// nil (every sign unsure) when there is no bundle or it fails validation.
    static func loadMatcher(from url: URL?) -> SignMatcher? {
        guard let url else { return nil }
        do {
            return SignMatcher(try RecognitionBundle.load(from: Data(contentsOf: url)))
        } catch {
            recognitionLog.error("recognition bundle rejected: \(String(describing: error), privacy: .public)")
            return nil
        }
    }

    /// nil when there is no bundle or it fails validation (every sign is then unsure).
    static func loadLogitsBundle(from url: URL?) -> LogitsBundle? {
        guard let url else { return nil }
        do {
            return try LogitsBundle.load(from: Data(contentsOf: url))
        } catch {
            recognitionLog.error("ASL bundle rejected: \(String(describing: error), privacy: .public)")
            return nil
        }
    }

    static func makeLogitsModel(_ url: URL) throws -> any LogitsModel {
        #if canImport(SignPipelineLiteRT) && os(iOS)
        return try LiteRTLogitsModel(contentsOf: url)
        #else
        throw RecognitionSetupError.liteRTUnavailable
        #endif
    }

    func makeLandmarkProvider() throws -> any LandmarkProvider {
        guard let holisticModel else { throw RecognitionSetupError.missingHolisticModel }
        #if canImport(SignPipelineMediaPipe) && os(iOS)
        return try HolisticLandmarkProvider(modelPath: holisticModel.path)
        #else
        throw RecognitionSetupError.mediaPipeUnavailable
        #endif
    }
}

enum RecognitionSetupError: LocalizedError {
    case missingHolisticModel
    case mediaPipeUnavailable
    case liteRTUnavailable

    var errorDescription: String? {
        switch self {
        case .missingHolisticModel:
            "holistic_landmarker.task is missing from LocalAssets. Run the SignPipelineMediaPipe download script."
        case .mediaPipeUnavailable:
            "MediaPipe isn't available in this build."
        case .liteRTUnavailable:
            "The LiteRT runtime isn't available in this build."
        }
    }
}
