import Foundation
import RecognitionCore
import SignPipeline
#if canImport(SignPipelineMediaPipe)
import SignPipelineMediaPipe
#endif

/// Model and data files the recognition pipeline loads from the app bundle. They are
/// personal or large, so they're not in Git: put them in `ios/Ishara/LocalAssets/`
/// (see the README there) and Xcode copies that folder into the app.
struct RecognitionAssets: Sendable {
    static let folder = "LocalAssets"

    var holisticModel: URL?
    /// `SignCLIPEncoder.mlmodelc` (or an `.mlpackage`, compiled on first launch).
    var encoderModel: URL?
    var recognitionBundle: URL?
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
            sampleClips: clips
        )
    }

    /// Shown on Get ready when recognition will run but can only answer [?].
    var notice: String? {
        if recognitionBundle == nil {
            return "No recognition bundle installed, so every sign will show [?]."
        }
        if encoderModel == nil {
            return "No SignCLIP encoder installed, so every sign will show [?]."
        }
        return nil
    }

    /// Builds the landmark provider, encoder and matcher. Runs on the worker thread.
    /// A missing or broken encoder or bundle leaves the classifier answering `.unsure`.
    func makeComponents() throws -> PipelineComponents {
        PipelineComponents(landmarks: try makeLandmarkProvider(), classifier: makeClassifier())
    }

    func makeClassifier() -> SegmentClassifier {
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

    private func makeLandmarkProvider() throws -> any LandmarkProvider {
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

    var errorDescription: String? {
        switch self {
        case .missingHolisticModel:
            "holistic_landmarker.task is missing from LocalAssets. Run the SignPipelineMediaPipe download script."
        case .mediaPipeUnavailable:
            "MediaPipe isn't available in this build."
        }
    }
}
