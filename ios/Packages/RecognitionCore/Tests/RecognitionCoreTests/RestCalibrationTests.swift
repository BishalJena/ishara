import RecognitionCore
import XCTest

final class RestCalibrationTests: XCTestCase {
    /// `count` frames at 100 fps from t = 0; the first `unseen` frames have no shoulders.
    private func recording(
        frames count: Int,
        unseen: Int = 0,
        wristYs: (Int) -> [Double] = { _ in [0.85, 0.85] }
    ) -> [DetectorFrame] {
        (0..<count).map { k in
            DetectorFrame(
                t: Double(k) / 100,
                body: k >= unseen,
                wrists: wristYs(k).map { NormalizedPoint(x: 0.5, y: $0) }
            )
        }
    }

    private func assertCalibrationFails(
        _ frames: [DetectorFrame],
        params: DetectorParams = DetectorParams(),
        with expected: CalibrationError,
        file: StaticString = #filePath,
        line: UInt = #line
    ) {
        XCTAssertThrowsError(try SignDetector.calibrate(frames: frames, params: params), file: file, line: line) {
            XCTAssertEqual($0 as? CalibrationError, expected, file: file, line: line)
        }
    }

    // MARK: Length

    func testRecordingCoveringExactly2sIsLongEnough() throws {
        // 0.00 ... 2.00
        XCTAssertEqual(try SignDetector.calibrate(frames: recording(frames: 201)), 0.77, accuracy: 1e-12)
    }

    func testRecordingCovering1_99sIsTooShort() {
        assertCalibrationFails(recording(frames: 200), with: .tooShort)
    }

    func testEmptyRecordingIsTooShort() {
        assertCalibrationFails([], with: .tooShort)
    }

    func testCalibrationLengthIsConfigurable() throws {
        var params = DetectorParams()
        params.calibrationS = 1.0

        XCTAssertNoThrow(try SignDetector.calibrate(frames: recording(frames: 101), params: params))
        assertCalibrationFails(recording(frames: 100), params: params, with: .tooShort)
    }

    func testTooShortIsReportedBeforeCantSee() {
        assertCalibrationFails(recording(frames: 100, unseen: 100), with: .tooShort)
    }

    // MARK: Body visibility

    func testExactly80PercentOfFramesWithShouldersIsEnough() {
        // 205 frames, 41 unseen: 164/205 = 0.8
        XCTAssertNoThrow(try SignDetector.calibrate(frames: recording(frames: 205, unseen: 41)))
    }

    func testFewerThan80PercentOfFramesWithShouldersCantSee() {
        // 42 unseen: 163/205 < 0.8
        assertCalibrationFails(recording(frames: 205, unseen: 42), with: .cantSee)
    }

    func testMinimumBodyFractionIsConfigurable() {
        var params = DetectorParams()
        params.minBodyFraction = 0.5

        XCTAssertNoThrow(try SignDetector.calibrate(frames: recording(frames: 205, unseen: 100), params: params))
        assertCalibrationFails(recording(frames: 205, unseen: 103), params: params, with: .cantSee)
    }

    // MARK: Rest line

    func testRestLineIsMedianWristHeightMinusMargin() throws {
        // odd count: 0.60, 0.90, 0.90 -> median 0.90 (mean would be 0.80)
        let frames = recording(frames: 201) { k in k == 0 ? [0.60] : (k == 1 ? [0.90, 0.90] : []) }

        XCTAssertEqual(try SignDetector.calibrate(frames: frames), 0.82, accuracy: 1e-12)
    }

    func testEvenCountMedianAveragesTheMiddleTwo() throws {
        // 0.70, 0.80, 0.90, 0.95 -> median 0.85
        let frames = recording(frames: 201) { k in k == 0 ? [0.95, 0.70] : (k == 1 ? [0.90, 0.80] : []) }

        XCTAssertEqual(try SignDetector.calibrate(frames: frames), 0.77, accuracy: 1e-12)
    }

    func testRestMarginIsConfigurable() throws {
        var params = DetectorParams()
        params.restMargin = 0.10

        XCTAssertEqual(try SignDetector.calibrate(frames: recording(frames: 201), params: params), 0.75, accuracy: 1e-12)
    }

    func testRestLineIsClampedToTheMinimum() throws {
        let frames = recording(frames: 201) { _ in [0.30] }

        XCTAssertEqual(try SignDetector.calibrate(frames: frames), 0.50)
    }

    func testRestLineIsClampedToTheMaximum() throws {
        var params = DetectorParams()
        params.restMargin = 0
        let frames = recording(frames: 201) { _ in [0.98] }

        XCTAssertEqual(try SignDetector.calibrate(frames: frames, params: params), 0.95)
    }

    func testRestLineInsideTheBandIsNotClamped() throws {
        XCTAssertEqual(try SignDetector.calibrate(frames: recording(frames: 201) { _ in [0.59] }), 0.51, accuracy: 1e-12)
        XCTAssertEqual(try SignDetector.calibrate(frames: recording(frames: 201) { _ in [1.02] }), 0.94, accuracy: 1e-12)
    }

    func testNoWristsSeenFallsBackToTheDefaultRestLine() throws {
        XCTAssertEqual(try SignDetector.calibrate(frames: recording(frames: 201) { _ in [] }), 0.80)

        var params = DetectorParams()
        params.defaultRestY = 0.66
        XCTAssertEqual(try SignDetector.calibrate(frames: recording(frames: 201) { _ in [] }, params: params), 0.66)
    }
}
