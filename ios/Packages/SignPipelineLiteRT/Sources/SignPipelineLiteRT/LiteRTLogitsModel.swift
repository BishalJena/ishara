import Foundation
import SignPipeline
#if canImport(TensorFlowLiteC)
import TensorFlowLiteC
#endif

public enum LiteRTLogitsModelError: Error, Equatable {
    case runtimeUnavailable
    case modelNotLoaded(String)
    case interpreterNotCreated
    /// The model doesn't take one `[frames, 543, 3]` float input and give one float output.
    case unexpectedSignature(String)
    case badInput(values: Int, frames: Int)
    case resizeFailed(frames: Int)
    case allocationFailed
    case invokeFailed
    case nonFiniteOutput
}

/// `LogitsModel` backed by TensorFlow Lite (LiteRT), running the ASL Signs 1st-place
/// `asl-signs.tflite` on the CPU (XNNPACK). The input's time dimension is dynamic, so the
/// input tensor is resized whenever the clip length changes. Not thread-safe: build and use
/// it on one thread, as the recognition worker does.
public final class LiteRTLogitsModel: LogitsModel {
    public static let threads: Int32 = 2

    #if canImport(TensorFlowLiteC)
    private let model: OpaquePointer
    private let interpreter: OpaquePointer
    private var allocatedFrames: Int?
    public let classCount: Int

    public init(contentsOf url: URL) throws {
        guard let model = TfLiteModelCreateFromFile(url.path) else {
            throw LiteRTLogitsModelError.modelNotLoaded(url.lastPathComponent)
        }
        let options = TfLiteInterpreterOptionsCreate()
        defer { TfLiteInterpreterOptionsDelete(options) }
        TfLiteInterpreterOptionsSetNumThreads(options, Self.threads)
        guard let interpreter = TfLiteInterpreterCreate(model, options) else {
            TfLiteModelDelete(model)
            throw LiteRTLogitsModelError.interpreterNotCreated
        }
        self.model = model
        self.interpreter = interpreter
        do {
            classCount = try Self.checkSignature(interpreter)
        } catch {
            TfLiteInterpreterDelete(interpreter)
            TfLiteModelDelete(model)
            throw error
        }
    }

    deinit {
        TfLiteInterpreterDelete(interpreter)
        TfLiteModelDelete(model)
    }

    public func logits(landmarks: [Float], frameCount: Int) throws -> [Float] {
        try Self.checkInput(landmarks: landmarks, frameCount: frameCount)
        if allocatedFrames != frameCount {
            let dims: [Int32] = [Int32(frameCount), Int32(KaggleLayout.points), Int32(KaggleLayout.coordinates)]
            guard TfLiteInterpreterResizeInputTensor(interpreter, 0, dims, Int32(dims.count)) == kTfLiteOk else {
                throw LiteRTLogitsModelError.resizeFailed(frames: frameCount)
            }
            guard TfLiteInterpreterAllocateTensors(interpreter) == kTfLiteOk else {
                allocatedFrames = nil
                throw LiteRTLogitsModelError.allocationFailed
            }
            allocatedFrames = frameCount
        }
        guard let input = TfLiteInterpreterGetInputTensor(interpreter, 0) else {
            throw LiteRTLogitsModelError.unexpectedSignature("no input tensor")
        }
        let copied = landmarks.withUnsafeBytes { bytes in
            TfLiteTensorCopyFromBuffer(input, bytes.baseAddress, bytes.count)
        }
        guard copied == kTfLiteOk else { throw LiteRTLogitsModelError.badInput(values: landmarks.count, frames: frameCount) }
        guard TfLiteInterpreterInvoke(interpreter) == kTfLiteOk else { throw LiteRTLogitsModelError.invokeFailed }
        guard let output = TfLiteInterpreterGetOutputTensor(interpreter, 0) else {
            throw LiteRTLogitsModelError.unexpectedSignature("no output tensor")
        }
        var logits = [Float](repeating: 0, count: classCount)
        let read = logits.withUnsafeMutableBytes { bytes in
            TfLiteTensorCopyToBuffer(output, bytes.baseAddress, bytes.count)
        }
        guard read == kTfLiteOk else { throw LiteRTLogitsModelError.unexpectedSignature("output size changed") }
        guard logits.allSatisfy(\.isFinite) else { throw LiteRTLogitsModelError.nonFiniteOutput }
        return logits
    }

    /// One float32 input `[frames, 543, 3]`, one float32 output; returns the class count.
    private static func checkSignature(_ interpreter: OpaquePointer) throws -> Int {
        guard TfLiteInterpreterGetInputTensorCount(interpreter) == 1,
              TfLiteInterpreterGetOutputTensorCount(interpreter) == 1,
              let input = TfLiteInterpreterGetInputTensor(interpreter, 0),
              let output = TfLiteInterpreterGetOutputTensor(interpreter, 0)
        else { throw LiteRTLogitsModelError.unexpectedSignature("expected one input and one output") }
        guard TfLiteTensorType(input) == kTfLiteFloat32, TfLiteTensorType(output) == kTfLiteFloat32 else {
            throw LiteRTLogitsModelError.unexpectedSignature("expected float32 tensors")
        }
        let inputDims = (0..<TfLiteTensorNumDims(input)).map { Int(TfLiteTensorDim(input, $0)) }
        guard inputDims.count == 3, inputDims[1] == KaggleLayout.points, inputDims[2] == KaggleLayout.coordinates else {
            throw LiteRTLogitsModelError.unexpectedSignature("input \(inputDims), expected [frames, 543, 3]")
        }
        let classes = TfLiteTensorByteSize(output) / MemoryLayout<Float>.size
        guard classes >= 2 else { throw LiteRTLogitsModelError.unexpectedSignature("output has \(classes) values") }
        return classes
    }
    #else
    public init(contentsOf url: URL) throws {
        throw LiteRTLogitsModelError.runtimeUnavailable
    }

    public func logits(landmarks: [Float], frameCount: Int) throws -> [Float] {
        throw LiteRTLogitsModelError.runtimeUnavailable
    }
    #endif

    /// The values must be exactly `frameCount` Kaggle frames.
    public static func checkInput(landmarks: [Float], frameCount: Int) throws {
        guard frameCount > 0, landmarks.count == frameCount * KaggleLayout.valuesPerFrame else {
            throw LiteRTLogitsModelError.badInput(values: landmarks.count, frames: frameCount)
        }
    }
}
