import XCTest

@testable import CallSession

/// Golden strings are the exact output of `model_dump_json()` on the backend's pydantic
/// models (backend/app/protocol.py), so a renamed or missing key fails here.
final class MessagesTests: XCTestCase {
    private let t1 = TurnID("t1")!

    // MARK: App -> backend

    func testChipsEncodesLikeBackendModel() throws {
        try assertEncodes(
            AppMessage.chips(turnID: t1, chips: [.hello, .doctor, .tomorrow]),
            python: #"{"type":"chips","turn_id":"t1","chips":["hello","doctor","tomorrow"]}"#)
    }

    func testApproveEncodesLikeBackendModel() throws {
        try assertEncodes(
            AppMessage.approve(turnID: t1, text: "Hello, I'd like a doctor's appointment tomorrow."),
            python:
                #"{"type":"approve","turn_id":"t1","text":"Hello, I'd like a doctor's appointment tomorrow."}"#
        )
    }

    func testStopEncodesLikeBackendModel() throws {
        try assertEncodes(AppMessage.stop, python: #"{"type":"stop"}"#)
    }

    func testEndEncodesLikeBackendModel() throws {
        try assertEncodes(AppMessage.end, python: #"{"type":"end"}"#)
    }

    func testEverySignEncodesAsBackendSignLiteral() throws {
        let data = try WireCoding.makeEncoder().encode(Sign.allCases)
        XCTAssertEqual(
            String(decoding: data, as: UTF8.self),
            #"["hello","thankyou","yes","no","sorry","doctor","today","tomorrow","morning","afternoon","evening","time"]"#
        )
    }

    func testEncodingDoesNotEscapeSlashes() throws {
        let text = try WireCoding.encodeText(.approve(turnID: t1, text: "10/30"))
        XCTAssertEqual(text, #"{"text":"10/30","turn_id":"t1","type":"approve"}"#)
    }

    func testStartCallRequestEncodesLikeBackendModel() throws {
        let data = try WireCoding.makeEncoder().encode(
            StartCallRequest(contactID: "city_clinic", purpose: .doctorAppointment))
        XCTAssertEqual(
            String(decoding: data, as: UTF8.self),
            #"{"contact_id":"city_clinic","purpose":"doctor_appointment"}"#)
    }

    func testStartCallResponseDecodes() throws {
        let start = try JSONDecoder().decode(
            CallStart.self, from: Data(#"{"call_id":"call_123","state":"dialing"}"#.utf8))
        XCTAssertEqual(start, CallStart(callID: "call_123", state: .dialing))
    }

    // MARK: Backend -> app

    func testStatusDecodesEveryState() throws {
        let states = ["dialing", "ringing", "in_call", "speaking", "ended", "error"]
        let decoded = try states.map {
            try WireCoding.decodeServerMessage(#"{"type":"status","state":"\#($0)"}"#)
        }
        XCTAssertEqual(
            decoded,
            [.status(.dialing), .status(.ringing), .status(.inCall), .status(.speaking),
             .status(.ended), .status(.error)])
    }

    func testCaptionDecodes() throws {
        XCTAssertEqual(
            try WireCoding.decodeServerMessage(
                #"{"type":"caption","text":"We have 4 pm tomorrow. Does that work?","at":1793430000.25}"#),
            .caption(text: "We have 4 pm tomorrow. Does that work?", at: 1_793_430_000.25))
    }

    func testCaptionDecodesIntegerTimestamp() throws {
        XCTAssertEqual(
            try WireCoding.decodeServerMessage(#"{"type":"caption","text":"Hi","at":1793430000}"#),
            .caption(text: "Hi", at: 1_793_430_000))
    }

    func testDraftDecodesBothSources() throws {
        XCTAssertEqual(
            try WireCoding.decodeServerMessage(
                #"{"type":"draft","turn_id":"t1","text":"Hello.","source":"llm"}"#),
            .draft(turnID: t1, text: "Hello.", source: .llm))
        XCTAssertEqual(
            try WireCoding.decodeServerMessage(
                #"{"type":"draft","turn_id":"t1","text":"Hello.","source":"template"}"#),
            .draft(turnID: t1, text: "Hello.", source: .template))
    }

    func testSpokenDecodes() throws {
        XCTAssertEqual(
            try WireCoding.decodeServerMessage(#"{"type":"spoken","turn_id":"t1"}"#),
            .spoken(turnID: t1))
    }

    func testNotDeliveredDecodesEveryBackendReason() throws {
        XCTAssertEqual(
            try WireCoding.decodeServerMessage(
                #"{"type":"not_delivered","turn_id":"t1","reason":"no_confirmation"}"#),
            .notDelivered(turnID: t1, reason: "no_confirmation"))
        XCTAssertEqual(
            try WireCoding.decodeServerMessage(
                #"{"type":"not_delivered","turn_id":"t1","reason":"bolna_unreachable"}"#),
            .notDelivered(turnID: t1, reason: "bolna_unreachable"))
    }

    /// Every code the backend sends today: the turn rejections of app/sessions.py and the
    /// two from app/calls.py, each with its exact message.
    func testErrorDecodesEveryBackendCode() throws {
        let frames = [
            #"{"type":"error","code":"stale_turn","message":"That turn is closed; start a new one."}"#,
            #"{"type":"error","code":"already_approved","message":"That turn was already sent."}"#,
            #"{"type":"error","code":"call_not_live","message":"The call is not connected yet."}"#,
            #"{"type":"error","code":"call_ended","message":"The call has ended. Nothing will be sent."}"#,
            #"{"type":"error","code":"cannot_interrupt","message":"Bolna is already speaking; it cannot be interrupted."}"#,
            #"{"type":"error","code":"busy_speaking","message":"Wait until the current reply has been spoken."}"#,
            #"{"type":"error","code":"bad_message","message":"Unrecognised message."}"#,
            #"{"type":"error","code":"end_failed","message":"Could not reach Bolna to hang up."}"#,
        ]
        let codes = try frames.map { frame -> String in
            guard case let .error(code, message) = try WireCoding.decodeServerMessage(frame) else {
                XCTFail("not an error: \(frame)")
                return ""
            }
            XCTAssertFalse(message.isEmpty)
            return code
        }
        XCTAssertEqual(
            codes,
            ["stale_turn", "already_approved", "call_not_live", "call_ended", "cannot_interrupt",
             "busy_speaking", "bad_message", "end_failed"])
    }

    func testUnknownTypeDecodesToUnknownInsteadOfThrowing() throws {
        XCTAssertEqual(
            try WireCoding.decodeServerMessage(#"{"type":"latency_report","ms":120}"#),
            .unknown(type: "latency_report"))
    }

    func testMissingTypeIsRejected() {
        XCTAssertThrowsError(try WireCoding.decodeServerMessage(#"{"state":"in_call"}"#))
    }

    func testKnownTypeWithMissingFieldIsRejected() {
        XCTAssertThrowsError(try WireCoding.decodeServerMessage(#"{"type":"draft","text":"Hello."}"#))
    }

    func testUnknownStateIsRejected() {
        XCTAssertThrowsError(try WireCoding.decodeServerMessage(#"{"type":"status","state":"held"}"#))
    }

    func testDraftWithInvalidTurnIDIsRejected() {
        XCTAssertThrowsError(
            try WireCoding.decodeServerMessage(
                #"{"type":"draft","turn_id":"bad id","text":"Hello.","source":"llm"}"#))
    }

    // MARK: Helpers

    /// The encoded bytes must equal the backend's JSON with keys sorted, which proves the
    /// key names, values and the absence of extra keys (`extra="forbid"` on the backend).
    private func assertEncodes(
        _ message: AppMessage, python: String, file: StaticString = #filePath, line: UInt = #line
    ) throws {
        XCTAssertEqual(try WireCoding.encodeText(message), try sortedKeys(python), file: file, line: line)
    }

    private func sortedKeys(_ json: String) throws -> String {
        let object = try JSONSerialization.jsonObject(with: Data(json.utf8))
        let data = try JSONSerialization.data(
            withJSONObject: object, options: [.sortedKeys, .withoutEscapingSlashes])
        return String(decoding: data, as: UTF8.self)
    }
}
