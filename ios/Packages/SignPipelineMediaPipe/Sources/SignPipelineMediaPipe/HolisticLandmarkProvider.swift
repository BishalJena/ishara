#if canImport(MediaPipeTasksVision)
import Accelerate
import CoreVideo
import MediaPipeTasksVision
import SignPipeline

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

        let image = try MPImage(pixelBuffer: try Self.uprightPixelBuffer(of: frame), orientation: .up)
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

    // MediaPipe also exports a `Landmark` (world coordinates), so qualify ours.
    private func landmark(_ point: NormalizedLandmark, visibility: Float? = nil) -> SignPipeline.Landmark {
        SignPipeline.Landmark(x: point.x, y: point.y, z: point.z, visibility: visibility)
    }
}

extension HolisticLandmarkProvider {
    /// The Holistic task has no region-of-interest input, so MediaPipe rejects
    /// any `MPImage` whose orientation is not `.up`. Rotate the pixels instead.
    static func uprightPixelBuffer(of frame: VideoFrame) throws -> CVPixelBuffer {
        let rotation: Int
        switch frame.orientation {
        case .up: return frame.pixelBuffer
        case .right: rotation = kRotate90DegreesClockwise
        case .down: rotation = kRotate180DegreesClockwise
        case .left: rotation = kRotate270DegreesClockwise
        }

        let source = frame.pixelBuffer
        let format = CVPixelBufferGetPixelFormatType(source)
        guard format == kCVPixelFormatType_32BGRA else {
            throw HolisticLandmarkProviderError.unsupportedPixelFormat(format)
        }
        let size = frame.uprightSize
        var upright: CVPixelBuffer?
        let created = CVPixelBufferCreate(
            nil, size.width, size.height, format,
            [kCVPixelBufferIOSurfacePropertiesKey: [:]] as CFDictionary, &upright
        )
        guard created == kCVReturnSuccess, let upright else {
            throw HolisticLandmarkProviderError.rotationFailed(Int(created))
        }

        CVPixelBufferLockBaseAddress(source, .readOnly)
        CVPixelBufferLockBaseAddress(upright, [])
        defer {
            CVPixelBufferUnlockBaseAddress(upright, [])
            CVPixelBufferUnlockBaseAddress(source, .readOnly)
        }
        var sourceImage = vImage_Buffer(
            data: CVPixelBufferGetBaseAddress(source),
            height: vImagePixelCount(CVPixelBufferGetHeight(source)),
            width: vImagePixelCount(CVPixelBufferGetWidth(source)),
            rowBytes: CVPixelBufferGetBytesPerRow(source)
        )
        var uprightImage = vImage_Buffer(
            data: CVPixelBufferGetBaseAddress(upright),
            height: vImagePixelCount(size.height),
            width: vImagePixelCount(size.width),
            rowBytes: CVPixelBufferGetBytesPerRow(upright)
        )
        // Channel order does not matter for a pure rotation, so ARGB covers BGRA.
        var background: [UInt8] = [0, 0, 0, 0]
        let rotated = vImageRotate90_ARGB8888(
            &sourceImage, &uprightImage, UInt8(rotation), &background, vImage_Flags(kvImageNoFlags)
        )
        guard rotated == kvImageNoError else {
            throw HolisticLandmarkProviderError.rotationFailed(rotated)
        }
        return upright
    }
}

public enum HolisticLandmarkProviderError: Error, Equatable {
    case nonIncreasingTimestamp(Int, previous: Int)
    /// Only rotated frames need a known layout; camera and file sources emit BGRA.
    case unsupportedPixelFormat(OSType)
    case rotationFailed(Int)
}
#endif
