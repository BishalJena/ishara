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

    func testRecordedCalibrationIsCappedAndCanRestart() {
        let model = GetReadyModel()
        GetReadyModel.Check.allCases.forEach(model.pass)

        model.recordCalibration(seconds: 1)
        XCTAssertEqual(model.calibrationProgress, 0.5, accuracy: 1e-9)
        model.recordCalibration(seconds: 5)
        XCTAssertTrue(model.isCalibrated)

        model.restartCalibration()

        XCTAssertEqual(model.calibrationProgress, 0)
        XCTAssertFalse(model.isReady)
    }

    func testRecordedCalibrationWaitsForTheChecklist() {
        let model = GetReadyModel()
        model.pass(.face)

        model.recordCalibration(seconds: 2)

        XCTAssertFalse(model.isCalibrated)
    }
}
