import CallSession
import Foundation
import Observation

/// Recent calls, kept on this phone only: one JSON file per call (`<id>.json`) in a folder,
/// written atomically. Without a folder the calls live in memory for this launch only
/// (UI tests, `-IsharaCallHistory memory`).
@MainActor
@Observable
final class CallHistory {
    /// Newest first.
    private(set) var records: [CallRecord] = []
    /// Saved calls that couldn't be read, or a call that couldn't be written.
    private(set) var problem: String?

    @ObservationIgnored private let folder: URL?

    init(folder: URL?) {
        self.folder = folder
        if let folder { load(from: folder) }
    }

    /// `Application Support/CallHistory`, or memory only if that folder can't be found.
    static func inApplicationSupport() -> CallHistory {
        do {
            let support = try FileManager.default.url(
                for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
            return CallHistory(folder: support.appending(path: "CallHistory", directoryHint: .isDirectory))
        } catch {
            let history = CallHistory(folder: nil)
            history.problem = "Calls can't be saved on this phone."
            return history
        }
    }

    /// Adds the call, or replaces the saved one with the same id.
    func save(_ record: CallRecord) {
        records.removeAll { $0.id == record.id }
        let index = records.firstIndex { $0.date < record.date } ?? records.endIndex
        records.insert(record, at: index)
        write(record)
    }

    /// The call's notes changed, for example Bolna's summary arrived after the call.
    func update(_ id: UUID, notes: CallNotes) {
        guard var record = records.first(where: { $0.id == id }), record.notes != notes else { return }
        record.notes = notes
        save(record)
    }

    func delete(_ id: UUID) {
        records.removeAll { $0.id == id }
        guard let folder else { return }
        do {
            try FileManager.default.removeItem(at: Self.file(for: id, in: folder))
        } catch CocoaError.fileNoSuchFile {
            // Never written (a failed save); nothing to remove.
        } catch {
            problem = "A call couldn't be deleted from this phone."
        }
    }

    private func load(from folder: URL) {
        let files: [URL]
        do {
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
            files = try FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil)
                .filter { $0.pathExtension == "json" }
        } catch {
            problem = "Saved calls couldn't be read."
            return
        }
        let decoder = JSONDecoder()
        var unreadable = 0
        for file in files {
            do {
                records.append(try decoder.decode(CallRecord.self, from: Data(contentsOf: file)))
            } catch {
                unreadable += 1
            }
        }
        records.sort { $0.date > $1.date }
        if unreadable > 0 {
            problem = unreadable == 1 ? "1 saved call couldn't be read." : "\(unreadable) saved calls couldn't be read."
        }
    }

    private func write(_ record: CallRecord) {
        guard let folder else { return }
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        do {
            try encoder.encode(record).write(to: Self.file(for: record.id, in: folder), options: .atomic)
        } catch {
            problem = "The call with \(record.contactName) couldn't be saved on this phone."
        }
    }

    private static func file(for id: UUID, in folder: URL) -> URL {
        folder.appending(path: "\(id.uuidString).json", directoryHint: .notDirectory)
    }
}
