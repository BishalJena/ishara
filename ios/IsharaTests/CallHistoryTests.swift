import CallSession
import XCTest
@testable import Ishara

@MainActor
final class CallHistoryTests: XCTestCase {
    private var folder: URL!

    override func setUp() async throws {
        folder = FileManager.default.temporaryDirectory.appending(path: "CallHistoryTests-\(UUID().uuidString)")
    }

    override func tearDown() async throws {
        try? FileManager.default.removeItem(at: folder)
    }

    private func record(minutesAgo: Double, contact: String = "City Clinic", notes: CallNotes? = nil) -> CallRecord {
        let date = Date(timeIntervalSinceNow: -minutesAgo * 60)
        return CallRecord(
            id: UUID(), date: date, contactName: contact, mode: notes == nil ? .live : .delegated,
            captions: [CallRecord.Line(speaker: .receptionist, text: "We have 4 pm tomorrow.", at: date),
                       CallRecord.Line(speaker: .user, text: "Yes, that works. Thank you.", at: date)],
            notes: notes)
    }

    private func delegatedNotes(bolna: String? = nil) -> CallNotes {
        CallNotes(callID: "c1", mode: .delegated, ready: true, outcome: "callback",
                  summary: ["They offered: \"4 pm tomorrow\""], transcript: [
                    TranscriptEntry(speaker: .receptionist, text: "We have 4 pm tomorrow.", at: 1),
                  ], bolnaSummary: bolna)
    }

    private func jsonFiles() throws -> [URL] {
        try FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil)
            .filter { $0.pathExtension == "json" }
    }

    func testSavedCallsSurviveARelaunch() throws {
        let history = CallHistory(folder: folder)
        let live = record(minutesAgo: 10)
        let delegated = record(minutesAgo: 5, contact: "Dr. Mehta's office", notes: delegatedNotes(bolna: "Call back."))
        history.save(live)
        history.save(delegated)

        let relaunched = CallHistory(folder: folder)

        XCTAssertEqual(relaunched.records, [delegated, live])
        XCTAssertEqual(try jsonFiles().map(\.lastPathComponent).sorted(),
                       ["\(live.id.uuidString).json", "\(delegated.id.uuidString).json"].sorted())
        XCTAssertNil(relaunched.problem)
    }

    func testNewestCallFirstWhateverTheSavingOrder() {
        let history = CallHistory(folder: folder)
        let old = record(minutesAgo: 60), newest = record(minutesAgo: 1), middle = record(minutesAgo: 30)
        for call in [old, newest, middle] { history.save(call) }

        XCTAssertEqual(history.records.map(\.id), [newest.id, middle.id, old.id])
        XCTAssertEqual(CallHistory(folder: folder).records.map(\.id), [newest.id, middle.id, old.id])
    }

    func testSavingTheSameCallAgainReplacesIt() throws {
        let history = CallHistory(folder: folder)
        var call = record(minutesAgo: 1)
        history.save(call)
        call.captions.append(CallRecord.Line(speaker: .agent, text: "Goodbye.", at: Date()))
        history.save(call)

        XCTAssertEqual(history.records, [call])
        XCTAssertEqual(CallHistory(folder: folder).records, [call])
        XCTAssertEqual(try jsonFiles().count, 1)
    }

    func testDeletingACallRemovesItsFile() throws {
        let history = CallHistory(folder: folder)
        let kept = record(minutesAgo: 10), deleted = record(minutesAgo: 5)
        history.save(kept)
        history.save(deleted)

        history.delete(deleted.id)

        XCTAssertEqual(history.records, [kept])
        XCTAssertEqual(try jsonFiles().map(\.lastPathComponent), ["\(kept.id.uuidString).json"])
        XCTAssertEqual(CallHistory(folder: folder).records, [kept])
        XCTAssertNil(history.problem)
    }

    func testBolnasLateSummaryUpdatesTheSavedCall() {
        let history = CallHistory(folder: folder)
        let call = record(minutesAgo: 1, notes: delegatedNotes())
        history.save(call)

        history.update(call.id, notes: delegatedNotes(bolna: "The caller will be called back."))

        XCTAssertEqual(history.records.first?.notes?.bolnaSummary, "The caller will be called back.")
        let relaunched = CallHistory(folder: folder)
        XCTAssertEqual(relaunched.records.first?.notes?.bolnaSummary, "The caller will be called back.")
        XCTAssertEqual(relaunched.records.first?.captions, call.captions)
    }

    func testNotesForAnUnknownCallAreIgnored() throws {
        let history = CallHistory(folder: folder)
        history.update(UUID(), notes: delegatedNotes())
        XCTAssertTrue(history.records.isEmpty)
        XCTAssertTrue(try jsonFiles().isEmpty)
    }

    func testAnUnreadableFileIsSkippedAndReported() throws {
        let good = record(minutesAgo: 1)
        CallHistory(folder: folder).save(good)
        try Data("not a call".utf8).write(to: folder.appending(path: "broken.json"))
        try Data("ignored".utf8).write(to: folder.appending(path: "notes.txt"))

        let relaunched = CallHistory(folder: folder)

        XCTAssertEqual(relaunched.records, [good])
        XCTAssertEqual(relaunched.problem, "1 saved call couldn't be read.")
    }

    func testAFolderThatCantBeWrittenIsReported() throws {
        try Data().write(to: folder)  // a file where the folder should be
        let history = CallHistory(folder: folder)
        XCTAssertEqual(history.problem, "Saved calls couldn't be read.")

        let call = record(minutesAgo: 1)
        history.save(call)

        XCTAssertEqual(history.records, [call], "the call is still shown for this launch")
        XCTAssertEqual(history.problem, "The call with City Clinic couldn't be saved on this phone.")
    }

    func testInMemoryHistoryStartsEmptyEveryLaunch() {
        CallHistory(folder: nil).save(record(minutesAgo: 1))
        XCTAssertTrue(CallHistory(folder: nil).records.isEmpty)
    }

    func testCallHistoryLaunchArgument() throws {
        let suite = "call-history-\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        XCTAssertEqual(DemoLaunchOptions.from(defaults).callHistory, .applicationSupport)
        defaults.set("memory", forKey: "IsharaCallHistory")
        XCTAssertEqual(DemoLaunchOptions.from(defaults).callHistory, .memory)
        defaults.set(folder.path, forKey: "IsharaCallHistory")
        XCTAssertEqual(DemoLaunchOptions.from(defaults).callHistory, .folder(URL(fileURLWithPath: folder.path, isDirectory: true)))

        let services = AppServices.current(options: .from(defaults))
        services.history.save(record(minutesAgo: 1))
        XCTAssertEqual(try jsonFiles().count, 1, "the history went to the folder given at launch")
    }
}
