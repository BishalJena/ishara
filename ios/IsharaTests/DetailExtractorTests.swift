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
        XCTAssertEqual(details.map(\.label), ["Policy number", "Name", "Date of birth", "Valid until"])
        XCTAssertEqual(details.first?.value, "AH-4821-7732")
        XCTAssertEqual(details[2].value, "12/03/1994")
    }

    func testLabelOnItsOwnLineTakesTheNextLine() {
        let details = DetailExtractor.extract(from: "Member ID\n99120034\nSomething else")
        XCTAssertEqual(details, [Detail(label: "Member ID", value: "99120034")])
    }

    func testTypedRequestYieldsTheDetailsItMentions() {
        let text = "Book a check-up next week, mornings only. My policy number is AH-4821 and my date of birth is 12/03/1994, callback number 9845012345."
        let details = DetailExtractor.extract(from: text)
        XCTAssertEqual(details, [
            Detail(label: "Policy number", value: "AH-4821"),
            Detail(label: "Date of birth", value: "12/03/1994"),
            Detail(label: "Phone", value: "9845012345"),
        ])
    }

    func testIndianNumbers() {
        XCTAssertEqual(Contact.indianDigits(from: "+91 98450 12345"), "9845012345")
        XCTAssertEqual(Contact.indianDigits(from: "098450 12345"), "9845012345")
        XCTAssertEqual(Contact.indian("9845012345")?.phoneNumber, "+919845012345")
        XCTAssertNil(Contact.indian("0845012345"))
        XCTAssertNil(Contact.indian("98450"))
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
