import XCTest

@testable import CallSession

final class VocabularyTests: XCTestCase {
    func testSignsMatchBackendSignsTupleInOrder() {
        // backend/app/protocol.py SIGNS
        let backendSigns = [
            "hello", "thankyou", "yes", "no", "sorry", "doctor",
            "today", "tomorrow", "morning", "afternoon", "evening", "time",
            "please", "now", "wait", "night", "yesterday", "later", "can", "where", "who",
            "why", "have", "finish", "callonphone", "sick", "hungry", "drink", "water",
            "home", "go", "see", "hear", "read",
        ]
        XCTAssertEqual(Sign.allCases.map(\.rawValue), backendSigns)
        XCTAssertEqual(Sign.templateSigns.map(\.rawValue), Array(backendSigns.prefix(12)))
        XCTAssertTrue(Sign.rehearsed.allSatisfy { Sign.allCases.contains($0) })
    }

    func testPurposeRawValueMatchesBackend() {
        XCTAssertEqual(CallPurpose.allCases.map(\.rawValue), ["doctor_appointment"])
    }

    func testLimitsMatchBackend() {
        XCTAssertEqual(ProtocolLimits.maxChips, 8)
        XCTAssertEqual(ProtocolLimits.maxSpokenCharacters, 300)
    }

    func testTurnIDAcceptsBackendPattern() {
        XCTAssertNotNil(TurnID("a"))
        XCTAssertNotNil(TurnID("Turn_01-x"))
        XCTAssertNotNil(TurnID(String(repeating: "z", count: 64)))
    }

    func testTurnIDRejectsAnythingOutsideBackendPattern() {
        XCTAssertNil(TurnID(""))
        XCTAssertNil(TurnID(String(repeating: "z", count: 65)))
        XCTAssertNil(TurnID("has space"))
        XCTAssertNil(TurnID("dot.ted"))
        XCTAssertNil(TurnID("slash/"))
        XCTAssertNil(TurnID("é"))
        XCTAssertNil(TurnID("٣"))  // Arabic-Indic digit: alphanumeric but not ASCII
    }

    func testRandomTurnIDIsLowercaseHexWithoutDashes() throws {
        let id = TurnID.random()
        XCTAssertEqual(id.rawValue.count, 32)
        XCTAssertTrue(id.rawValue.allSatisfy { "0123456789abcdef".contains($0) })
        XCTAssertNotNil(TurnID(id.rawValue))
    }

    func testRandomTurnIDsDiffer() {
        XCTAssertNotEqual(TurnID.random(), TurnID.random())
    }

    func testTurnIDDecodingRejectsInvalidValue() {
        let json = Data(#"["bad id"]"#.utf8)
        XCTAssertThrowsError(try JSONDecoder().decode([TurnID].self, from: json))
    }

    func testTurnIDEncodesAsPlainString() throws {
        let data = try JSONEncoder().encode([TurnID("t1")!])
        XCTAssertEqual(String(decoding: data, as: UTF8.self), #"["t1"]"#)
    }
}
