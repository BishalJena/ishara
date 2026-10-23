import XCTest
@testable import Ishara

@MainActor
final class GetReadyModelTests: XCTestCase {
    func testCalibrationWaitsForTheChecklist() {
        let model = GetReadyModel()
        model.pass(.face)
        model.advanceCalibration(by: 2)

        XCTAssertEqual(model.calibrationProgress, 0)
        XCTAssertFalse(model.isReady)
    }

    func testReadyOnlyAfterAllChecksAndTwoSecondsAtRest() {
        let model = GetReadyModel()
        GetReadyModel.Check.allCases.forEach(model.pass)

        model.advanceCalibration(by: 1.9)
        XCTAssertFalse(model.isReady)

        model.advanceCalibration(by: 0.1)
        XCTAssertTrue(model.isReady)
        XCTAssertEqual(model.calibrationProgress, 1)
    }
}
