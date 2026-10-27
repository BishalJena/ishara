import XCTest
@testable import SignPipeline

final class KaggleLayoutTests: XCTestCase {
    func testLayoutMatchesTheCompetitionData() {
        XCTAssertEqual(KaggleLayout.points, 543)
        XCTAssertEqual(KaggleLayout.Offset.leftHand, 468)
        XCTAssertEqual(KaggleLayout.Offset.pose, 489)
        XCTAssertEqual(KaggleLayout.Offset.rightHand, 522)
        XCTAssertEqual(KaggleLayout.valuesPerFrame, 1629)
    }

    func testOrdersFaceLeftHandPoseRightHand() {
        let frame = Synthetic.frame()
        let values = KaggleLayout.values(for: [frame])

        XCTAssertEqual(values.count, KaggleLayout.valuesPerFrame)
        XCTAssertEqual(point(values, 0), xyz(frame.face![0]))
        XCTAssertEqual(point(values, 467), xyz(frame.face![467]))
        XCTAssertEqual(point(values, KaggleLayout.Offset.leftHand), xyz(frame.leftHand![0]))
        XCTAssertEqual(point(values, KaggleLayout.Offset.pose + 11), xyz(frame.pose![11]))
        XCTAssertEqual(point(values, KaggleLayout.Offset.rightHand + 20), xyz(frame.rightHand![20]))
    }

    func testMissingPartsAreNaN() {
        let values = KaggleLayout.values(for: [Synthetic.frame(face: nil, rightHand: nil)])

        let face = values[0..<(468 * 3)]
        let rightHand = values[(KaggleLayout.Offset.rightHand * 3)...]
        XCTAssertTrue(face.allSatisfy(\.isNaN))
        XCTAssertTrue(rightHand.allSatisfy(\.isNaN))
        XCTAssertFalse(values[(KaggleLayout.Offset.leftHand * 3)..<(KaggleLayout.Offset.rightHand * 3)].contains { $0.isNaN })
    }

    func testDropsTheTenIrisPointsOfTheHolisticLandmarker() throws {
        let face = Synthetic.face() + (0..<10).map { _ in Landmark(x: 9, y: 9, z: 9) }
        let frame = try LandmarkFrame(timestamp: 0, imageSize: Synthetic.size, face: face)
        let values = KaggleLayout.values(for: [frame])

        XCTAssertEqual(values.count, KaggleLayout.valuesPerFrame)
        XCTAssertFalse(values.contains(9))
    }

    func testFramesFollowEachOther() {
        let frames = [Synthetic.frame(timestamp: 0), Synthetic.frame(timestamp: 1, leftHand: nil)]
        let values = KaggleLayout.values(for: frames)

        XCTAssertEqual(values.count, 2 * KaggleLayout.valuesPerFrame)
        XCTAssertFalse(point(values, KaggleLayout.Offset.leftHand)[0].isNaN)
        XCTAssertTrue(point(values, KaggleLayout.points + KaggleLayout.Offset.leftHand)[0].isNaN)
    }

    private func point(_ values: [Float], _ index: Int) -> [Float] {
        Array(values[(index * 3)..<(index * 3 + 3)])
    }

    private func xyz(_ landmark: Landmark) -> [Float] {
        [landmark.x, landmark.y, landmark.z]
    }
}
