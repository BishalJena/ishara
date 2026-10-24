/// Collects the landmark frames of one sign while the detector has a clip open.
///
/// Holds at most `EncoderInput.maxFrames` frames. Frames past the limit are
/// counted but not stored, and the clip is then rejected as a whole: cutting it
/// short could drop the part of the sign that carries its meaning.
public struct ClipBuffer: Sendable {
    public private(set) var frames: [LandmarkFrame] = []
    /// Every frame offered since the last reset, including any past the limit.
    public private(set) var receivedCount = 0

    public init() {}

    public var hasOverflowed: Bool { receivedCount > EncoderInput.maxFrames }

    /// Returns `false` once the clip is too long to encode.
    @discardableResult
    public mutating func append(_ frame: LandmarkFrame) -> Bool {
        receivedCount += 1
        guard !hasOverflowed else { return false }
        frames.append(frame)
        return true
    }

    public mutating func reset() {
        frames.removeAll(keepingCapacity: true)
        receivedCount = 0
    }

    public func makeEncoderInput() throws -> EncoderInput {
        guard !hasOverflowed else { throw EncoderInputError.tooManyFrames(receivedCount) }
        return try EncoderInput(frames: FeatureBuilder.features(for: frames))
    }
}
