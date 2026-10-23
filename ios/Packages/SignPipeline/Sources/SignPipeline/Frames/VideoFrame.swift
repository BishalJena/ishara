import CoreGraphics
import CoreMedia
import CoreVideo

/// How a stored frame must be rotated to appear upright, with the same meaning
/// as `UIImage.Orientation` (`.right`: rotate 90° clockwise to display).
public enum FrameOrientation: Equatable, Sendable {
    case up, down, left, right

    /// Reads the rotation of a video track's `preferredTransform`. Mirroring is
    /// not supported: MediaPipe rejects mirrored orientations.
    public init(preferredTransform t: CGAffineTransform) throws {
        guard t.a * t.d - t.b * t.c > 0 else { throw FrameSourceError.mirroredVideo }
        switch (t.a.rounded(), t.b.rounded()) {
        case (1, 0): self = .up
        case (0, 1): self = .right
        case (-1, 0): self = .down
        case (0, -1): self = .left
        default: throw FrameSourceError.unsupportedRotation
        }
    }

    var swapsDimensions: Bool { self == .left || self == .right }
}

/// A decoded frame ready for landmark detection.
public struct VideoFrame: @unchecked Sendable {
    public let pixelBuffer: CVPixelBuffer
    public let timestamp: CMTime
    public let orientation: FrameOrientation

    public init(pixelBuffer: CVPixelBuffer, timestamp: CMTime, orientation: FrameOrientation = .up) {
        self.pixelBuffer = pixelBuffer
        self.timestamp = timestamp
        self.orientation = orientation
    }

    /// Size of the frame once rotated upright; landmarks are normalized to it.
    public var uprightSize: ImageSize {
        let width = CVPixelBufferGetWidth(pixelBuffer)
        let height = CVPixelBufferGetHeight(pixelBuffer)
        return orientation.swapsDimensions
            ? ImageSize(width: height, height: width)
            : ImageSize(width: width, height: height)
    }
}

/// Produces frames in presentation order.
public protocol FrameSource {
    func frames() -> AsyncThrowingStream<VideoFrame, Error>
}

/// Turns one frame into holistic landmarks. MediaPipe sits behind this protocol.
/// Callers pass frames in order with strictly increasing timestamps, as
/// MediaPipe's video running mode requires.
public protocol LandmarkProvider: AnyObject {
    func landmarks(for frame: VideoFrame) throws -> LandmarkFrame
}

public enum FrameSourceError: Error, Equatable {
    case noVideoTrack
    case mirroredVideo
    case unsupportedRotation
    case readerFailed(String)
    case cameraUnavailable
    case cameraNotAuthorized
    case cameraConfigurationFailed(String)
}
