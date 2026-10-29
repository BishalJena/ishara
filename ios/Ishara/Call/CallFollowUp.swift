import Foundation

/// What happens once a call is over, whatever screen is open: it is saved to Recent calls,
/// and a Call for me call's notes are followed until Bolna's summary is in (or the tries run
/// out), each change saved to the call. The follow-up keeps going when the user leaves the
/// notes, goes Home or starts another call; it only reads its own call's notes.
///
/// Live calls aren't followed: the backend's notes for them hold only the transcript, never an
/// outcome or Bolna's summary, and the call screen's captions are saved already.
@MainActor
enum CallFollowUp {
    /// Saves the call and returns the notes being followed, for the notes screen to show; nil
    /// for a live call or a call that was never placed.
    static func callEnded(
        _ call: ActiveCallViewModel,
        history: CallHistory,
        sleep: @escaping @Sendable (Duration) async throws -> Void = { try await Task.sleep(for: $0) }
    ) -> NotesModel? {
        guard let record = call.record else { return nil }
        history.save(record)
        guard call.isDelegated else { return nil }
        let notes = NotesModel(
            contactName: record.contactName, driver: call.driver,
            onNotes: { history.update(record.id, notes: $0) }, sleep: sleep)
        notes.start()
        return notes
    }
}
