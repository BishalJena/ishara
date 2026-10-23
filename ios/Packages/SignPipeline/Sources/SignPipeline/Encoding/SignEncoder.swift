/// A dense Float32 tensor in row-major order.
public struct Tensor: Equatable, Sendable {
    public let shape: [Int]
    public let values: [Float]

    public init(shape: [Int], values: [Float]) throws {
        guard shape.allSatisfy({ $0 > 0 }), shape.reduce(1, *) == values.count else {
            throw TensorError.shapeMismatch(shape: shape, count: values.count)
        }
        self.shape = shape
        self.values = values
    }
}

public enum TensorError: Error, Equatable {
    case shapeMismatch(shape: [Int], count: Int)
}

/// Anything that maps SignCLIP encoder tensors to the raw `embedding` output.
/// `CoreMLEmbeddingModel` is the production implementation.
public protocol EmbeddingModel {
    /// - Parameters:
    ///   - features: shape `EncoderInput.featureShape`
    ///   - mask: shape `EncoderInput.maskShape`
    /// - Returns: the raw embedding with shape [1, D].
    func embedding(features: Tensor, mask: Tensor) throws -> Tensor
}

/// SignCLIP video embedding for one clip, exactly as the encoder returned it.
/// It is **not** L2-normalized; matching normalizes downstream.
public struct SignEmbedding: Equatable, Sendable {
    public let values: [Float]
}

/// Runs an `EmbeddingModel` on one encoded clip and checks its output the way
/// `signclip.py embed` does (finite, non-zero), without altering the values.
public struct SignEncoder {
    private let model: any EmbeddingModel

    public init(model: any EmbeddingModel) {
        self.model = model
    }

    public func embed(_ input: EncoderInput) throws -> SignEmbedding {
        let output = try model.embedding(
            features: Tensor(shape: EncoderInput.featureShape, values: input.features),
            mask: Tensor(shape: EncoderInput.maskShape, values: input.mask)
        )
        guard output.shape.count == 2, output.shape[0] == 1 else {
            throw SignEncoderError.unexpectedOutputShape(output.shape)
        }
        guard output.values.allSatisfy(\.isFinite) else { throw SignEncoderError.nonFiniteEmbedding }
        guard output.values.contains(where: { $0 != 0 }) else { throw SignEncoderError.zeroEmbedding }
        return SignEmbedding(values: output.values)
    }

    public func embed(_ clip: ClipBuffer) throws -> SignEmbedding {
        try embed(clip.makeEncoderInput())
    }
}

public enum SignEncoderError: Error, Equatable {
    case unexpectedOutputShape([Int])
    case nonFiniteEmbedding
    case zeroEmbedding
}
