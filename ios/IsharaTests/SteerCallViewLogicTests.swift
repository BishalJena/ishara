import CallSession
import XCTest

@testable import Ishara

/// The call screen's pure helpers: folding cover lines, facts from spoken times, display names.
final class SteerCallViewLogicTests: XCTestCase {
    private func caption(_ text: String, _ speaker: Caption.Speaker) -> Caption {
        Caption(text: text, at: Date(timeIntervalSince1970: 0), speaker: speaker)
    }

    func testARunOfCoverLinesShowsAsItsLastLine() {
        let captions = [
            caption("sure can i have your file number please", .receptionist),
            caption("One moment, please.", .agent),
            caption("Bear with me a moment.", .agent),
            caption("Sorry for the wait, they're still replying.", .agent),
            caption("It's pp4471920.", .user),
            caption("One moment, please.", .agent),
        ]
        let rows = CoverLines.rows(captions)
        XCTAssertEqual(rows.map(\.index), [0, 3, 4, 5])
        XCTAssertEqual(rows.map(\.folded), [0, 2, 0, 0])
    }

    func testTimesInWordsBecomeFacts() {
        XCTAssertEqual(CallFacts.digitsForSpokenTimes("we have four pm tomorrow does that work"), "we have 4 pm tomorrow does that work")
        XCTAssertEqual(CallFacts.digitsForSpokenTimes("ten thirty am on monday"), "10:30 am on monday")
        XCTAssertEqual(CallFacts.digitsForSpokenTimes("come at eleven o'clock"), "come at 11")
        XCTAssertEqual(CallFacts.digitsForSpokenTimes("I have one question"), "I have one question")
        let facts = CallFacts.extract(from: ["okay we have wednesday at eleven am does that work"]).map(\.text)
        XCTAssertEqual(Set(facts), ["11 am", "wednesday"])
    }

    func testANumberShowsSpacedWithAPersonGlyph() {
        XCTAssertEqual(Contact.display("+919337473802"), "+91 93374 73802")
        XCTAssertEqual(Contact.indian("9337473802")?.name, "+91 93374 73802")
        XCTAssertEqual(Contact.indian("9337473802", name: "Dr Mehta")?.name, "Dr Mehta")
        XCTAssertEqual(InitialsAvatar.initials("+91 93374 73802"), "")
        XCTAssertEqual(InitialsAvatar.initials("City Clinic"), "CC")
    }
}
