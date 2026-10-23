import XCTest
@testable import Ishara

final class DemoScriptTests: XCTestCase {
    func testScriptedChipsGetTheRehearsedLLMSentence() {
        let draft = DemoScript.draft(for: ["no", "morning"])
        XCTAssertEqual(draft.text, "No, sorry, 4 pm doesn't work. Is there anything tomorrow morning?")
        XCTAssertEqual(draft.source, .llm)
    }

    func testWrongChipFallsBackToTemplateInSignOrder() {
        let draft = DemoScript.draft(for: ["no", "afternoon", "morning"])
        XCTAssertEqual(draft.text, "No. In the afternoon, please. In the morning, please.")
        XCTAssertEqual(draft.source, .template)
    }

    func testEveryScriptedSignHasATemplatePhrase() {
        let words = DemoScript.stages.flatMap(\.signs).compactMap { result -> String? in
            if case .sign(let word) = result { word } else { nil }
        }
        for word in words {
            XCTAssertNotNil(DemoScript.templatePhrases[word], word)
        }
    }

    func testScriptPlansOneWrongChipAndOneUnsureSign() {
        let signs = DemoScript.stages.flatMap(\.signs)
        XCTAssertTrue(signs.contains(.sign("afternoon")))
        XCTAssertEqual(signs.filter { $0 == .unsure }.count, 1)
    }
}
