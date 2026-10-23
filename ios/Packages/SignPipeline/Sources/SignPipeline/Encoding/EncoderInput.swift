/// Tensors for `SignCLIPEncoder.mlpackage`: `features` Float32 [1, 256, 609]
/// zero-padded at the end, and `mask` Float32 [1, 256] with 1 for real frames
/// and 0 for padding. Clips longer than 256 frames are rejected, never truncated,
/// and clips shorter than 4 frames are rejected like `signclip.py` does.
public struct EncoderInput: Equatable, Sendable {
    public static let maxFrames = 256
    public static let minFrames = 4
    public static let featureShape = [1, maxFrames, SignCLIPLayout.valuesPerFrame]
    public static let maskShape = [1, maxFrames]

    public let frameCount: Int
    /// Row-major `featureShape` values.
    public let features: [Float]
    /// Row-major `maskShape` values.
    public let mask: [Float]

    public init(frames: [[Float]]) throws {
        guard frames.count <= Self.maxFrames else { throw EncoderInputError.tooManyFrames(frames.count) }
        guard frames.count >= Self.minFrames else { throw EncoderInputError.tooFewFrames(frames.count) }
        let width = SignCLIPLayout.valuesPerFrame
        var features = [Float](repeating: 0, count: Self.maxFrames * width)
        for (index, frame) in frames.enumerated() {
            guard frame.count == width else {
                throw EncoderInputError.wrongFrameWidth(frame: index, count: frame.count)
            }
            guard frame.allSatisfy(\.isFinite) else { throw EncoderInputError.nonFiniteFeature(frame: index) }
            features.replaceSubrange(index * width..<(index + 1) * width, with: frame)
        }
        self.frameCount = frames.count
        self.features = features
        self.mask = (0..<Self.maxFrames).map { $0 < frames.count ? 1 : 0 }
    }
}

public enum EncoderInputError: Error, Equatable {
    case tooManyFrames(Int)
    case tooFewFrames(Int)
    case wrongFrameWidth(frame: Int, count: Int)
    case nonFiniteFeature(frame: Int)
}
