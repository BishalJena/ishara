import XCTest
@testable import SignPipeline

final class FeatureBuilderTests: XCTestCase {
    // MARK: Golden parity with the Python reference

    func testMatchesPythonReferenceWithinTolerance() throws {
        let fixture = try FeatureFixture.load()
        let golden = fixture.cases.filter { $0.expected != nil }
        XCTAssertEqual(golden.count, 2, "fixture should hold a full and a missing-parts clip")

        for fixtureCase in golden {
            let expected = try XCTUnwrap(fixtureCase.expected)
            let actual = try FeatureBuilder.features(for: fixtureCase.landmarkFrames())
            XCTAssertEqual(actual.count, expected.count, fixtureCase.name)
            for (frame, (actualRow, expectedRow)) in zip(actual, expected).enumerated() {
                XCTAssertEqual(actualRow.count, 609, fixtureCase.name)
                let worst = zip(actualRow, expectedRow).map { abs($0 - $1) }.max() ?? .infinity
                XCTAssertLessThanOrEqual(worst, 1e-5, "\(fixtureCase.name) frame \(frame)")
            }
        }
    }

    func testRejectsFixtureClipWithoutTrackedShouldersLikePython() throws {
        let fixture = try FeatureFixture.load()
        let rejected = try XCTUnwrap(fixture.cases.first { $0.expectedError == "noTrackedShoulders" })
        XCTAssertThrowsError(try FeatureBuilder.features(for: rejected.landmarkFrames())) {
            XCTAssertEqual($0 as? FeatureBuilderError, .noTrackedShoulders)
        }
    }

    // MARK: Normalization

    func testScalesPixelsAndCentresOnShouldersWithoutScalingDepthByImageSize() throws {
        var pose = Synthetic.pose()
        pose[0] = Landmark(x: 0.5, y: 0.25, z: 0.1, visibility: 1)  // (100, 25) px
        let vector = try XCTUnwrap(FeatureBuilder.features(for: [Synthetic.frame(pose: pose)]).first)

        let nose = Block.point(vector, at: Block.pose, 0)
        XCTAssertEqual(nose[0], 0, accuracy: 1e-6)
        XCTAssertEqual(nose[1], -0.25, accuracy: 1e-6)
        XCTAssertEqual(nose[2], 0.001, accuracy: 1e-7)
        XCTAssertEqual(Block.point(vector, at: Block.pose, 11), [0.5, 0, 0])
        XCTAssertEqual(Block.point(vector, at: Block.pose, 12), [-0.5, 0, 0])
    }

    func testCentreAndScaleAreClipLevelAverages() throws {
        var wide = Synthetic.pose()
        wide[SignCLIPLayout.Pose.leftShoulder].x = 0.95   // 190 px: distance 140, midpoint 120
        let features = try FeatureBuilder.features(for: [
            Synthetic.frame(timestamp: 0), Synthetic.frame(timestamp: 1, pose: wide),
        ])
        // Clip centre x = (100 + 120) / 2 = 110, scale = 1 / ((100 + 140) / 2) = 1 / 120.
        let rightShoulderFirstFrame = Block.point(features[0], at: Block.pose, 12)
        XCTAssertEqual(rightShoulderFirstFrame[0], (50 - 110) / 120, accuracy: 1e-6)
    }

    func testFramesWithoutPoseDoNotAffectNormalization() throws {
        let tracked = [Synthetic.frame(timestamp: 0), Synthetic.frame(timestamp: 1)]
        let withGap = [tracked[0], Synthetic.frame(timestamp: 0.5, pose: nil), tracked[1]]

        let reference = try FeatureBuilder.features(for: tracked)
        let gapped = try FeatureBuilder.features(for: withGap)
        XCTAssertEqual(gapped[0], reference[0])
        XCTAssertEqual(gapped[2], reference[1])
        XCTAssertEqual(Array(gapped[1][Block.pose..<Block.face]), Array(repeating: 0, count: 99))
    }

    func testWeaklyVisibleShoulderStillCountsTowardNormalization() throws {
        var weak = Synthetic.pose()
        weak[SignCLIPLayout.Pose.leftShoulder] = Landmark(x: 0.95, y: 0.5, z: 0, visibility: 0.2)
        let features = try FeatureBuilder.features(for: [
            Synthetic.frame(timestamp: 0), Synthetic.frame(timestamp: 1, pose: weak),
        ])
        XCTAssertEqual(Block.point(features[0], at: Block.pose, 12)[0], (50 - 110) / 120, accuracy: 1e-6)
    }

    func testZeroVisibilityPointKeepsRawPixelValues() throws {
        var pose = Synthetic.pose()
        pose[7] = Landmark(x: 0.4, y: 0.3, z: -0.2, visibility: 0)
        let vector = try XCTUnwrap(FeatureBuilder.features(for: [Synthetic.frame(pose: pose)]).first)
        let point = Block.point(vector, at: Block.pose, 7)
        XCTAssertEqual(point[0], 80, accuracy: 1e-4)
        XCTAssertEqual(point[1], 30, accuracy: 1e-4)
        XCTAssertEqual(point[2], -0.2, accuracy: 1e-7)
    }

    func testMissingVisibilityCountsAsDetected() throws {
        let explicit = try FeatureBuilder.features(for: [Synthetic.frame(pose: Synthetic.pose(visibility: 1))])
        let implicit = try FeatureBuilder.features(for: [Synthetic.frame(pose: Synthetic.pose(visibility: nil))])
        XCTAssertEqual(implicit, explicit)
    }

    func testLegsAreZeroed() throws {
        let vector = try XCTUnwrap(FeatureBuilder.features(for: [Synthetic.frame()]).first)
        for index in 0..<LandmarkFrame.poseCount {
            let point = Block.point(vector, at: Block.pose, index)
            if SignCLIPLayout.Pose.legs.contains(index) {
                XCTAssertEqual(point, [0, 0, 0], "leg point \(index)")
            } else {
                XCTAssertNotEqual(point, [0, 0, 0], "upper-body point \(index)")
            }
        }
    }

    // MARK: Point selection and missing parts

    func testSelectsFaceContoursInSortedIndexOrder() throws {
        let vector = try XCTUnwrap(FeatureBuilder.features(for: [Synthetic.frame()]).first)
        XCTAssertEqual(SignCLIPLayout.faceContourIndices.count, 128)
        for (slot, meshIndex) in SignCLIPLayout.faceContourIndices.enumerated() {
            let expectedX = (Double(Float(meshIndex) / 1000) * 200 - 100) / 100
            XCTAssertEqual(Double(Block.point(vector, at: Block.face, slot)[0]), expectedX, accuracy: 1e-6)
        }
    }

    func testIgnoresIrisPointsFromTheHolisticLandmarker() throws {
        let iris = (0..<10).map { _ in Landmark(x: 0.9, y: 0.9, z: 0.9) }
        let refined = Synthetic.frame(face: Synthetic.face() + iris)
        XCTAssertEqual(try FeatureBuilder.features(for: [refined]),
                       try FeatureBuilder.features(for: [Synthetic.frame()]))
    }

    func testOrdersLeftHandBeforeRightHand() throws {
        let vector = try XCTUnwrap(FeatureBuilder.features(for: [Synthetic.frame()]).first)
        XCTAssertEqual(Block.point(vector, at: Block.leftHand, 0)[0], (120 - 100) / 100, accuracy: 1e-6)
        XCTAssertEqual(Block.point(vector, at: Block.rightHand, 0)[0], (60 - 100) / 100, accuracy: 1e-6)
    }

    func testMissingHandBecomesZerosWithoutChangingOtherValues() throws {
        let full = try XCTUnwrap(FeatureBuilder.features(for: [Synthetic.frame()]).first)
        let oneHanded = try XCTUnwrap(FeatureBuilder.features(for: [Synthetic.frame(leftHand: nil)]).first)

        XCTAssertEqual(Array(oneHanded[Block.leftHand..<Block.rightHand]), Array(repeating: 0, count: 63))
        XCTAssertEqual(Array(oneHanded[..<Block.leftHand]), Array(full[..<Block.leftHand]))
        XCTAssertEqual(Array(oneHanded[Block.rightHand...]), Array(full[Block.rightHand...]))
    }

    func testMissingFaceBecomesZerosWithoutChangingOtherValues() throws {
        let full = try XCTUnwrap(FeatureBuilder.features(for: [Synthetic.frame()]).first)
        let faceless = try XCTUnwrap(FeatureBuilder.features(for: [Synthetic.frame(face: nil)]).first)

        XCTAssertEqual(Array(faceless[Block.face..<Block.leftHand]), Array(repeating: 0, count: 384))
        XCTAssertEqual(Array(faceless[..<Block.face]), Array(full[..<Block.face]))
        XCTAssertEqual(Array(faceless[Block.leftHand...]), Array(full[Block.leftHand...]))
    }

    // MARK: Rejections

    func testRejectsClipWhoseShouldersNeverReachTrackingVisibility() {
        var pose = Synthetic.pose()
        pose[SignCLIPLayout.Pose.rightShoulder].visibility = 0.49
        XCTAssertThrowsError(try FeatureBuilder.features(for: [Synthetic.frame(pose: pose)])) {
            XCTAssertEqual($0 as? FeatureBuilderError, .noTrackedShoulders)
        }
    }

    func testAcceptsShoulderVisibilityExactlyAtThreshold() {
        var pose = Synthetic.pose()
        pose[SignCLIPLayout.Pose.rightShoulder].visibility = 0.5
        XCTAssertNoThrow(try FeatureBuilder.features(for: [Synthetic.frame(pose: pose)]))
    }

    func testRejectsCoincidentShoulders() {
        var pose = Synthetic.pose()
        pose[SignCLIPLayout.Pose.leftShoulder] = pose[SignCLIPLayout.Pose.rightShoulder]
        XCTAssertThrowsError(try FeatureBuilder.features(for: [Synthetic.frame(pose: pose)])) {
            XCTAssertEqual($0 as? FeatureBuilderError, .degenerateShoulders)
        }
    }
}
