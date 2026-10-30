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
            #"["hello","thankyou","yes","no","sorry","doctor","today","tomorrow","morning","afternoon","evening","time","please","now","wait","night","yesterday","later","can","where","who","why","have","finish","callonphone","sick","hungry","drink","water","home","go","see","hear","read"]"#
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
            #"{"attended":false,"contact_id":"city_clinic","mode":"live","purpose":"doctor_appointment"}"#)
    }

    func testDelegatedStartCallRequestEncodesLikeBackendModel() throws {
        let data = try WireCoding.makeEncoder().encode(
            StartCallRequest(
                contactID: "clinic", purpose: .doctorAppointment, mode: .delegated, briefID: "b9", attended: true))
        XCTAssertEqual(
            String(decoding: data, as: UTF8.self),
            #"{"attended":true,"brief_id":"b9","contact_id":"clinic","mode":"delegated","purpose":"doctor_appointment"}"#)
    }

    func testStartCallResponseDecodes() throws {
        let start = try JSONDecoder().decode(
            CallStart.self, from: Data(#"{"call_id":"call_123","state":"dialing"}"#.utf8))
        XCTAssertEqual(start, CallStart(callID: "call_123", state: .dialing))
        let delegated = try JSONDecoder().decode(
            CallStart.self, from: Data(#"{"call_id":"c2","state":"dialing","mode":"delegated"}"#.utf8))
        XCTAssertEqual(delegated.mode, .delegated)
    }

    func testBriefRequestEncodesAndBriefDecodes() throws {
        let data = try WireCoding.makeEncoder().encode(
            BriefRequest(purpose: .doctorAppointment, chips: [.tomorrow, .morning], profile: Profile(name: "Asha")))
        XCTAssertEqual(
            String(decoding: data, as: UTF8.self),
            #"{"chips":["tomorrow","morning"],"profile":{"details":[],"name":"Asha"},"purpose":"doctor_appointment"}"#)
        let brief = try JSONDecoder().decode(
            Brief.self,
            from: Data(#"{"brief_id":"b9","text":"Call on behalf of Asha.","goal":"book a doctor's appointment","constraints":["preferred time: tomorrow in the morning"]}"#.utf8))
        XCTAssertEqual(brief.briefID, "b9")
        XCTAssertEqual(brief.constraints, ["preferred time: tomorrow in the morning"])
    }

    func testAnswerEncodesLikeBackendModel() throws {
        let text = try WireCoding.encodeText(.answer(askID: "a1", choice: .no))
        XCTAssertEqual(text, #"{"ask_id":"a1","choice":"no","type":"answer"}"#)
    }

    func testAnOpenTimeQuestionDecodesItsTimeWordsAndAnAnswerEncodesOne() throws {
        let ask = try WireCoding.decodeServerMessage(
            #"{"type":"ask","ask_id":"t1","question":"what time would you like","options":[{"choice":"tomorrow","spoken":"Tomorrow, please."},{"choice":"morning","spoken":"In the morning, please."},{"choice":"now","spoken":"Today, please."},{"choice":"wait","spoken":"One moment."}],"fallback":"I'll call back.","timeout_s":10.0}"#)
        guard case let .ask(_, _, options, _, _) = ask else { return XCTFail("\(ask)") }
        XCTAssertEqual(options.map(\.choice), [.tomorrow, .morning, .now, .wait])
        let text = try WireCoding.encodeText(.answer(askID: "t1", choice: .tomorrow))
        XCTAssertEqual(text, #"{"ask_id":"t1","choice":"tomorrow","type":"answer"}"#)
    }

    func testAskAndAskResolvedDecode() throws {
        let ask = try WireCoding.decodeServerMessage(
            #"{"type":"ask","ask_id":"a1","question":"We have 4 pm tomorrow. Does that work?","options":[{"choice":"yes","spoken":"Yes, 4 pm tomorrow works. Thank you."},{"choice":"no","spoken":"No, sorry."},{"choice":"wait","spoken":"One moment."}],"fallback":"I'll call back.","timeout_s":10.0}"#)
        guard case let .ask(askID, question, options, fallback, timeoutS) = ask else { return XCTFail("\(ask)") }
        XCTAssertEqual(askID, "a1")
        XCTAssertEqual(question, "We have 4 pm tomorrow. Does that work?")
        XCTAssertEqual(options.map(\.choice), [.yes, .no, .wait])
        XCTAssertEqual(options[0].spoken, "Yes, 4 pm tomorrow works. Thank you.")
        XCTAssertEqual(fallback, "I'll call back.")
        XCTAssertEqual(timeoutS, 10)
        let resolved = try WireCoding.decodeServerMessage(
            #"{"type":"ask_resolved","ask_id":"a1","spoken":"Yes, 4 pm tomorrow works. Thank you.","source":"user"}"#)
        XCTAssertEqual(resolved, .askResolved(askID: "a1", spoken: "Yes, 4 pm tomorrow works. Thank you.", source: "user"))
    }

    func testCallNotesDecode() throws {
        let notes = try JSONDecoder().decode(
            CallNotes.self,
            from: Data(#"{"call_id":"c1","mode":"delegated","ready":true,"brief":"Call on behalf of Asha.","outcome":"booked","summary":["Goal: book a doctor's appointment for Asha."],"open_questions":[],"transcript":[{"speaker":"receptionist","text":"Booked.","at":1.0}],"bolna_summary":null}"#.utf8))
        XCTAssertEqual(notes.outcome, "booked")
        XCTAssertEqual(notes.transcript.first?.speaker, .receptionist)
        XCTAssertTrue(notes.openQuestions.isEmpty)
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

    func testCaptionWithoutSpeakerIsTheReceptionists() throws {
        let caption = try WireCoding.decodeServerMessage(#"{"type":"caption","text":"Hello?","at":1.0}"#)
        guard case let .caption(_, _, speaker) = caption else { return XCTFail("not a caption: \(caption)") }
        XCTAssertEqual(speaker, .receptionist)
    }

    func testCaptionDecodesReceptionistSpeaker() throws {
        XCTAssertEqual(
            try WireCoding.decodeServerMessage(
                #"{"type":"caption","text":"We have 4 pm tomorrow.","at":1793430000.25,"speaker":"receptionist"}"#),
            .caption(text: "We have 4 pm tomorrow.", at: 1_793_430_000.25, speaker: .receptionist))
    }

    func testCaptionDecodesAgentSpeaker() throws {
        XCTAssertEqual(
            try WireCoding.decodeServerMessage(
                #"{"type":"caption","text":"One moment please, I'm signing my reply.","at":1793430000.25,"speaker":"agent"}"#),
            .caption(text: "One moment please, I'm signing my reply.", at: 1_793_430_000.25, speaker: .agent))
    }

    func testCaptionWithUnknownSpeakerIsKeptAsTheReceptionists() throws {
        XCTAssertEqual(
            try WireCoding.decodeServerMessage(
                #"{"type":"caption","text":"Hello?","at":1.0,"speaker":"narrator"}"#),
            .caption(text: "Hello?", at: 1, speaker: .receptionist))
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
