import CoreML
import Foundation

/// `EmbeddingModel` backed by `SignCLIPEncoder.mlpackage` (ML Program, iOS 17, FP16),
/// using the feature names of the conversion contract.
///
/// The FP16 package must not run on the Neural Engine: measured on 47 clips, any
/// compute-unit setting that allows it gave cosine 0.63–0.81 against PyTorch, while
/// CPU+GPU gave ≥ 0.9999997 (ml/coreml parity run). Models are therefore always
/// loaded with `.cpuAndGPU`, and a model configured to use the Neural Engine is refused.
public final class CoreMLEmbeddingModel: EmbeddingModel {
    public enum FeatureName {
        public static let features = "features"
        public static let mask = "mask"
        public static let embedding = "embedding"
    }

    private let model: MLModel

    /// Wraps an already loaded model. Throws if its configuration allows the Neural Engine.
    public init(model: MLModel) throws {
        try Self.checkComputeUnits(model.configuration.computeUnits)
        self.model = model
    }

    /// Loads a compiled `.mlmodelc`, or compiles an `.mlpackage`/`.mlmodel` first, with
    /// `makeConfiguration()`. Compiling takes seconds, so ship the compiled model where possible.
    public convenience init(contentsOf url: URL) throws {
        let compiled = url.pathExtension == "mlmodelc" ? url : try MLModel.compileModel(at: url)
        try self.init(model: MLModel(contentsOf: compiled, configuration: Self.makeConfiguration()))
    }

    /// CPU and GPU only, full-precision GPU accumulation (the setting the parity run measured).
    public static func makeConfiguration() -> MLModelConfiguration {
        let configuration = MLModelConfiguration()
        configuration.computeUnits = .cpuAndGPU
        configuration.allowLowPrecisionAccumulationOnGPU = false
        return configuration
    }

    static func checkComputeUnits(_ units: MLComputeUnits) throws {
        switch units {
        case .cpuOnly, .cpuAndGPU:
            return
        case .all, .cpuAndNeuralEngine:
            throw CoreMLEmbeddingModelError.neuralEngineNotAllowed
        @unknown default:
            throw CoreMLEmbeddingModelError.neuralEngineNotAllowed
        }
    }

    public func embedding(features: Tensor, mask: Tensor) throws -> Tensor {
        let inputs = try MLDictionaryFeatureProvider(dictionary: [
            FeatureName.features: MLFeatureValue(multiArray: Self.multiArray(from: features)),
            FeatureName.mask: MLFeatureValue(multiArray: Self.multiArray(from: mask)),
        ])
        let outputs = try model.prediction(from: inputs)
        guard let embedding = outputs.featureValue(for: FeatureName.embedding)?.multiArrayValue else {
            throw CoreMLEmbeddingModelError.missingOutput(FeatureName.embedding)
        }
        return try Self.tensor(from: embedding)
    }

    static func multiArray(from tensor: Tensor) throws -> MLMultiArray {
        let array = try MLMultiArray(shape: tensor.shape.map { NSNumber(value: $0) }, dataType: .float32)
        array.withUnsafeMutableBufferPointer(ofType: Float.self) { buffer, strides in
            // A freshly allocated MLMultiArray is contiguous and row-major.
            precondition(strides == rowMajorStrides(tensor.shape), "unexpected MLMultiArray layout")
            _ = buffer.update(fromContentsOf: tensor.values)
        }
        return array
    }

    /// Reads any numeric multi-array element by element, honouring its strides.
    static func tensor(from array: MLMultiArray) throws -> Tensor {
        let shape = array.shape.map(\.intValue)
        let strides = array.strides.map(\.intValue)
        let read: (Int) -> Float
        switch array.dataType {
        case .float32:
            let pointer = array.dataPointer.assumingMemoryBound(to: Float.self)
            read = { pointer[$0] }
        case .float16:
            let pointer = array.dataPointer.assumingMemoryBound(to: UInt16.self)
            read = { Float(Float16(bitPattern: pointer[$0])) }
        case .double:
            let pointer = array.dataPointer.assumingMemoryBound(to: Double.self)
            read = { Float(pointer[$0]) }
        default:
            throw CoreMLEmbeddingModelError.unsupportedDataType(array.dataType.rawValue)
        }
        let count = shape.reduce(1, *)
        let logicalStrides = rowMajorStrides(shape)
        let values = (0..<count).map { linear -> Float in
            var offset = 0
            for (dimension, logicalStride) in logicalStrides.enumerated() {
                offset += (linear / logicalStride) % shape[dimension] * strides[dimension]
            }
            return read(offset)
        }
        return try Tensor(shape: shape, values: values)
    }
}

func rowMajorStrides(_ shape: [Int]) -> [Int] {
    var strides = [Int](repeating: 1, count: shape.count)
    for dimension in shape.indices.dropLast().reversed() {
        strides[dimension] = strides[dimension + 1] * shape[dimension + 1]
    }
    return strides
}

public enum CoreMLEmbeddingModelError: Error, Equatable {
    case missingOutput(String)
    case unsupportedDataType(Int)
    /// The FP16 SignCLIP encoder gives wrong embeddings on the Neural Engine.
    case neuralEngineNotAllowed
}
