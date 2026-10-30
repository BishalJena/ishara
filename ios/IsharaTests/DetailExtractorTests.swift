import CallSession
import XCTest

@testable import Ishara

/// What an attached insurance card or letter turns into: labelled chips, nothing invented.
final class DetailExtractorTests: XCTestCase {
    func testLabelledLinesBecomeChips() {
        let text = """
        ACME HEALTH INSURANCE
        Policy No: AH-4821-7732
        Name: Riya Sharma
        Date of birth: 12/03/1994
        Valid until 31/12/2026
        """
        let details = DetailExtractor.extract(from: text)
        XCTAssertEqual(details.map(\.label), ["Policy number", "Name on the card", "Date of birth", "Valid until"])
        XCTAssertEqual(details.first?.value, "AH-4821-7732")
        XCTAssertEqual(details[2].value, "12/03/1994")
    }

    func testLabelOnItsOwnLineTakesTheNextLine() {
        let details = DetailExtractor.extract(from: "Member ID\n99120034\nSomething else")
        XCTAssertEqual(details, [Detail(label: "Member ID", value: "99120034")])
    }

    func testPlainTextYieldsNothing() {
        XCTAssertTrue(DetailExtractor.extract(from: "Thank you for choosing us.\nSee you soon.").isEmpty)
    }

    func testOneChipPerLabelAndAtMostEight() {
        let text = (1...12).map { "Policy No: P\($0)" }.joined(separator: "\n") + "\nDOB: 1/1/2000"
        let details = DetailExtractor.extract(from: text)
        XCTAssertEqual(details.filter { $0.label == "Policy number" }.count, 1)
        XCTAssertLessThanOrEqual(details.count, 8)
    }
}
