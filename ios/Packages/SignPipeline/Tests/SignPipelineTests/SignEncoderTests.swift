import XCTest
@testable import SignPipeline

private final class StubModel: EmbeddingModel {
    var output: Tensor
    private(set) var calls: [(features: Tensor, mask: Tensor)] = []

    init(output: Tensor) {
        self.output = output
    }

    func embedding(features: Tensor, mask: Tensor) throws -> Tensor {
        calls.append((features, mask))
        return output
    }
}

final class SignEncoderTests: XCTestCase {
    private func input(frames count: Int = 5) throws -> EncoderInput {
        try EncoderInput(frames: (0..<count).map { frame in (0..<609).map { Float(frame * 609 + $0) } })
    }

    func testPassesContractShapedTensorsToTheModel() throws {
        let model = StubModel(output: try Tensor(shape: [1, 3], values: [1, 2, 3]))
        let input = try input(frames: 5)

        _ = try SignEncoder(model: model).embed(input)

        let call = try XCTUnwrap(model.calls.first)
        XCTAssertEqual(model.calls.count, 1)
        XCTAssertEqual(call.features.shape, [1, 256, 609])
        XCTAssertEqual(call.mask.shape, [1, 256])
        XCTAssertEqual(call.features.values, input.features)
        XCTAssertEqual(call.mask.values, input.mask)
    }

    func testReturnsTheRawEmbeddingWithoutNormalizing() throws {
        let raw: [Float] = [3, -4, 12, 0.5]
        let model = StubModel(output: try Tensor(shape: [1, 4], values: raw))

        let embedding = try SignEncoder(model: model).embed(input())

        XCTAssertEqual(embedding.values, raw)
    }

    func testEmbedsAClipBufferThroughFeatureBuilding() throws {
        let model = StubModel(output: try Tensor(shape: [1, 2], values: [1, 1]))
        var buffer = ClipBuffer()
        (0..<4).forEach { buffer.append(Synthetic.frame(timestamp: Double($0))) }

        _ = try SignEncoder(model: model).embed(buffer)

        XCTAssertEqual(model.calls.first?.features.values, try buffer.makeEncoderInput().features)
    }

    func testRejectsOutputThatIsNotASingleRow() throws {
        for shape in [[2, 2], [4], [1, 2, 2]] {
            let model = StubModel(output: try Tensor(shape: shape, values: [1, 2, 3, 4]))
            XCTAssertThrowsError(try SignEncoder(model: model).embed(input())) {
                XCTAssertEqual($0 as? SignEncoderError, .unexpectedOutputShape(shape))
            }
        }
    }

    func testRejectsNonFiniteOrAllZeroEmbeddings() throws {
        let nonFinite = StubModel(output: try Tensor(shape: [1, 2], values: [1, .nan]))
        XCTAssertThrowsError(try SignEncoder(model: nonFinite).embed(input())) {
            XCTAssertEqual($0 as? SignEncoderError, .nonFiniteEmbedding)
        }
        let zero = StubModel(output: try Tensor(shape: [1, 2], values: [0, 0]))
        XCTAssertThrowsError(try SignEncoder(model: zero).embed(input())) {
            XCTAssertEqual($0 as? SignEncoderError, .zeroEmbedding)
        }
    }

    func testTensorRejectsMismatchedShape() {
        XCTAssertThrowsError(try Tensor(shape: [1, 3], values: [1, 2])) {
            XCTAssertEqual($0 as? TensorError, .shapeMismatch(shape: [1, 3], count: 2))
        }
        XCTAssertThrowsError(try Tensor(shape: [0], values: []))
    }
}
