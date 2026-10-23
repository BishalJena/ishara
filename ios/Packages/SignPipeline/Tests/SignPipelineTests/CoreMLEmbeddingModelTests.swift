import CoreML
import XCTest
@testable import SignPipeline

final class CoreMLEmbeddingModelTests: XCTestCase {
    func testContractFeatureNames() {
        XCTAssertEqual(CoreMLEmbeddingModel.FeatureName.features, "features")
        XCTAssertEqual(CoreMLEmbeddingModel.FeatureName.mask, "mask")
        XCTAssertEqual(CoreMLEmbeddingModel.FeatureName.embedding, "embedding")
    }

    func testBuildsFloat32MultiArrayWithTensorShapeAndOrder() throws {
        let tensor = try Tensor(shape: [1, 2, 3], values: [0, 1, 2, 10, 11, 12])
        let array = try CoreMLEmbeddingModel.multiArray(from: tensor)

        XCTAssertEqual(array.dataType, .float32)
        XCTAssertEqual(array.shape, [1, 2, 3])
        XCTAssertEqual(array[[0, 1, 0] as [NSNumber]].floatValue, 10)
        XCTAssertEqual(array[[0, 0, 2] as [NSNumber]].floatValue, 2)
        XCTAssertEqual(array[[0, 1, 2] as [NSNumber]].floatValue, 12)
    }

    func testEncoderInputRoundTripsThroughMultiArray() throws {
        let input = try EncoderInput(frames: (0..<4).map { f in (0..<609).map { Float(f) + Float($0) / 609 } })
        let features = try Tensor(shape: EncoderInput.featureShape, values: input.features)

        let array = try CoreMLEmbeddingModel.multiArray(from: features)

        XCTAssertEqual(array.shape, [1, 256, 609])
        XCTAssertEqual(try CoreMLEmbeddingModel.tensor(from: array), features)
    }

    func testReadsFloat16AndDoubleOutputs() throws {
        let half = try MLMultiArray(shape: [1, 3], dataType: .float16)
        let double = try MLMultiArray(shape: [1, 3], dataType: .double)
        for (index, value) in [0.5, -2, 8].enumerated() {
            half[[0, index] as [NSNumber]] = NSNumber(value: value)
            double[[0, index] as [NSNumber]] = NSNumber(value: value)
        }

        XCTAssertEqual(try CoreMLEmbeddingModel.tensor(from: half), try Tensor(shape: [1, 3], values: [0.5, -2, 8]))
        XCTAssertEqual(try CoreMLEmbeddingModel.tensor(from: double), try Tensor(shape: [1, 3], values: [0.5, -2, 8]))
    }

    func testHonoursNonContiguousStrides() throws {
        // Logical [1, 2] view over storage [7, x, 9, x]: stride 2 on the last axis.
        let storage = UnsafeMutablePointer<Float>.allocate(capacity: 4)
        storage.initialize(from: [7, -1, 9, -1], count: 4)
        let array = try MLMultiArray(
            dataPointer: storage, shape: [1, 2], dataType: .float32, strides: [4, 2],
            deallocator: { $0.deallocate() }
        )

        XCTAssertEqual(try CoreMLEmbeddingModel.tensor(from: array).values, [7, 9])
    }

    func testRowMajorStrides() {
        XCTAssertEqual(rowMajorStrides([1, 256, 609]), [155_904, 609, 1])
        XCTAssertEqual(rowMajorStrides([1, 768]), [768, 1])
    }
}
