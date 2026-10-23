#if canImport(MediaPipeTasksVision)
import MediaPipeTasksVision
import SignPipeline
import UIKit

/// `LandmarkProvider` backed by MediaPipe's Holistic Landmarker in video mode.
///
/// Bundle `holistic_landmarker.task` (see `Scripts/download_holistic_model.sh`)
/// and pass its path. Video mode runs synchronously on the caller's thread and
/// needs strictly increasing millisecond timestamps; call it off the main thread.
public final class HolisticLandmarkProvider: LandmarkProvider {
    public struct Configuration {
        /// Task defaults; legacy Holistic used 0.5 for detection and tracking too.
        public var minPoseDetectionConfidence: Float = 0.5
        public var minPosePresenceConfidence: Float = 0.5
        public var minFaceDetectionConfidence: Float = 0.5
        public var minFacePresenceConfidence: Float = 0.5
        public var minHandLandmarksConfidence: Float = 0.5
        public var delegate: Delegate = .CPU

        public init() {}
    }

    private let landmarker: HolisticLandmarker
    private var lastTimestampMilliseconds: Int?

    public init(modelPath: String, configuration: Configuration = Configuration()) throws {
        let options = HolisticLandmarkerOptions()
        options.baseOptions.modelAssetPath = modelPath
        options.baseOptions.delegate = configuration.delegate
        options.runningMode = .video
        options.minPoseDetectionConfidence = configuration.minPoseDetectionConfidence
        options.minPosePresenceConfidence = configuration.minPosePresenceConfidence
        options.minFaceDetectionConfidence = configuration.minFaceDetectionConfidence
        options.minFacePresenceConfidence = configuration.minFacePresenceConfidence
        options.minHandLandmarksConfidence = configuration.minHandLandmarksConfidence
        options.outputFaceBlendshapes = false
        options.outputPoseSegmentationMasks = false
        landmarker = try HolisticLandmarker(options: options)
    }

    public func landmarks(for frame: VideoFrame) throws -> LandmarkFrame {
        let milliseconds = Int((frame.timestamp.seconds * 1000).rounded())
        if let last = lastTimestampMilliseconds, milliseconds <= last {
            throw HolisticLandmarkProviderError.nonIncreasingTimestamp(milliseconds, previous: last)
        }
        lastTimestampMilliseconds = milliseconds

        let image = try MPImage(pixelBuffer: frame.pixelBuffer, orientation: frame.orientation.imageOrientation)
        let result = try landmarker.detect(videoFrame: image, timestampInMilliseconds: milliseconds)
        return try LandmarkFrame.holistic(
            timestamp: frame.timestamp.seconds,
            imageSize: frame.uprightSize,
            pose: result.poseLandmarks.map { landmark($0, visibility: $0.visibility?.floatValue) },
            face: result.faceLandmarks.map { landmark($0) },
            leftHand: result.leftHandLandmarks.map { landmark($0) },
            rightHand: result.rightHandLandmarks.map { landmark($0) }
        )
    }

    private func landmark(_ point: NormalizedLandmark, visibility: Float? = nil) -> Landmark {
        Landmark(x: point.x, y: point.y, z: point.z, visibility: visibility)
    }
}

public enum HolisticLandmarkProviderError: Error, Equatable {
    case nonIncreasingTimestamp(Int, previous: Int)
}

extension FrameOrientation {
    var imageOrientation: UIImage.Orientation {
        switch self {
        case .up: .up
        case .down: .down
        case .left: .left
        case .right: .right
        }
    }
}
#endif
