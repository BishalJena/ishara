import XCTest

/// The person who answers a real call (the deployed backend and real Bolna). The test tells
/// them what to say and when by appending lines to a host file, which
/// `scripts/e2e_video_to_speech.sh --real` prints in the terminal as they come.
///
/// Set up by the runner from `TEST_RUNNER_ISHARA_E2E_PROMPTS` (the file),
/// `TEST_RUNNER_ISHARA_E2E_LINES` (their lines in order, separated by `|`) and
/// `TEST_RUNNER_ISHARA_E2E_HUMAN_WAIT` (seconds a person may take to answer or speak).
struct HumanReceptionist {
    let prompts: URL
    let lines: [String]
    let wait: TimeInterval

    init(environment: [String: String]) throws {
        let path = try XCTUnwrap(environment["ISHARA_E2E_PROMPTS"],
                                 "set TEST_RUNNER_ISHARA_E2E_PROMPTS to the file the runner prints")
        prompts = URL(fileURLWithPath: path)
        lines = try XCTUnwrap(environment["ISHARA_E2E_LINES"],
                              "set TEST_RUNNER_ISHARA_E2E_LINES to the receptionist's lines, separated by |")
            .split(separator: "|").map { $0.trimmingCharacters(in: .whitespaces) }
        wait = environment["ISHARA_E2E_HUMAN_WAIT"].flatMap(TimeInterval.init) ?? 90
    }

    /// The `index`th line they say (0-based), as the runner listed it.
    func line(_ index: Int, file: StaticString = #filePath, line sourceLine: UInt = #line) -> String {
        guard lines.indices.contains(index) else {
            XCTFail("the runner listed \(lines.count) receptionist lines, the test needs line \(index + 1)",
                    file: file, line: sourceLine)
            return ""
        }
        return lines[index]
    }

    /// One line in the runner's terminal.
    func tell(_ text: String) {
        let data = Data((text + "\n").utf8)
        guard let handle = try? FileHandle(forWritingTo: prompts) else {
            // The runner creates the file; without it the prompt still reaches the test log.
            print("receptionist prompt (no prompts file): \(text)")
            return
        }
        defer { try? handle.close() }
        _ = try? handle.seekToEnd()
        try? handle.write(contentsOf: data)
    }

    /// Waits up to `wait` for `condition`, repeating `what` every 20 s so the person
    /// knows the test is still waiting for them.
    func waitFor(_ what: String, file: StaticString = #filePath, line: UInt = #line,
                 _ condition: () -> Bool) {
        let start = Date()
        var nextReminder = start.addingTimeInterval(20)
        while Date().timeIntervalSince(start) < wait {
            if condition() { return }
            if Date() >= nextReminder {
                tell(String(format: "  … still waiting (%.0f of %.0f s): %@", Date().timeIntervalSince(start), wait, what))
                nextReminder = nextReminder.addingTimeInterval(20)
            }
            Thread.sleep(forTimeInterval: 0.1)
        }
        XCTFail("Timed out after \(Int(wait)) s waiting for \(what)", file: file, line: line)
    }
}
