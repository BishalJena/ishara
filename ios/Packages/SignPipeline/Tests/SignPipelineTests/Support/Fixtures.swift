import Foundation
@testable import SignPipeline

/// Golden data written by `Scripts/make_feature_fixture.py`.
struct FeatureFixture: Decodable {
    struct Frame: Decodable {
        let pose: [[Float]]?
        let face: [[Float]]?
        let leftHand: [[Float]]?
        let rightHand: [[Float]]?
    }

    struct Case: Decodable {
        let name: String
        let width: Int
        let height: Int
        let frames: [Frame]
        let expected: [[Float]]?
        let expectedError: String?

        func landmarkFrames() throws -> [LandmarkFrame] {
            try frames.enumerated().map { index, frame in
                try LandmarkFrame(
                    timestamp: Double(index) / 30,
                    imageSize: ImageSize(width: width, height: height),
                    pose: frame.pose.map(posePoints),
                    face: frame.face.map(points),
                    leftHand: frame.leftHand.map(points),
                    rightHand: frame.rightHand.map(points)
                )
            }
        }
    }

    let cases: [Case]

    static func load() throws -> FeatureFixture {
        let url = try XCTUnwrapResource("feature_fixture", extension: "json")
        return try JSONDecoder().decode(FeatureFixture.self, from: Data(contentsOf: url))
    }
}

private func points(_ rows: [[Float]]) -> [Landmark] {
    rows.map { Landmark(x: $0[0], y: $0[1], z: $0[2]) }
}

private func posePoints(_ rows: [[Float]]) -> [Landmark] {
    rows.map { Landmark(x: $0[0], y: $0[1], z: $0[2], visibility: $0[3]) }
}

struct MissingResource: Error {
    let name: String
}

func XCTUnwrapResource(_ name: String, extension ext: String) throws -> URL {
    guard let url = Bundle.module.url(forResource: name, withExtension: ext, subdirectory: "Resources")
    else { throw MissingResource(name: "\(name).\(ext)") }
    return url
}

/// Hand-built frames with easy numbers for focused tests.
enum Synthetic {
    static let size = ImageSize(width: 200, height: 100)

    /// Shoulders at (150, 50) and (50, 50) px: centre (100, 50, 0), distance 100.
    static func pose(visibility: Float? = 1) -> [Landmark] {
        var pose = (0..<LandmarkFrame.poseCount).map { index in
            Landmark(x: 0.3 + Float(index) / 100, y: 0.2 + Float(index) / 200,
                     z: Float(index) / 1000, visibility: visibility)
        }
        pose[SignCLIPLayout.Pose.leftShoulder] = Landmark(x: 0.75, y: 0.5, z: 0, visibility: visibility)
        pose[SignCLIPLayout.Pose.rightShoulder] = Landmark(x: 0.25, y: 0.5, z: 0, visibility: visibility)
        return pose
    }

    /// Landmark `i` sits at x = i / 1000 so the selected indices are readable.
    static func face() -> [Landmark] {
        (0..<LandmarkFrame.minimumFaceCount).map { Landmark(x: Float($0) / 1000, y: 0.4, z: 0.01) }
    }

    static func hand(x: Float) -> [Landmark] {
        (0..<LandmarkFrame.handCount).map { Landmark(x: x + Float($0) / 500, y: 0.6, z: -0.02) }
    }

    static func frame(
        timestamp: Double = 0,
        pose: [Landmark]? = Synthetic.pose(),
        face: [Landmark]? = Synthetic.face(),
        leftHand: [Landmark]? = Synthetic.hand(x: 0.6),
        rightHand: [Landmark]? = Synthetic.hand(x: 0.3)
    ) -> LandmarkFrame {
        // Inputs above are always well formed.
        try! LandmarkFrame(timestamp: timestamp, imageSize: size, pose: pose, face: face,
                           leftHand: leftHand, rightHand: rightHand)
    }
}

/// Offsets of each block inside a 609-value SignCLIP frame vector.
enum Block {
    static let pose = 0
    static let face = LandmarkFrame.poseCount * 3
    static let leftHand = face + SignCLIPLayout.faceContourIndices.count * 3
    static let rightHand = leftHand + LandmarkFrame.handCount * 3

    static func point(_ vector: [Float], at offset: Int, _ index: Int) -> [Float] {
        Array(vector[(offset + index * 3)..<(offset + index * 3 + 3)])
    }
}
