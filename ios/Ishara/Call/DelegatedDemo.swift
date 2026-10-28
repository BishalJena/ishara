import CallSession
import Foundation

/// The scripted delegated call (D9) the fake driver plays, so "Call for me" can be clicked
/// through in the simulator without a backend. The brief, the agent's lines and the notes
/// follow backend/app/delegate.py (`build_brief`, `RuleBrain`, `build_notes`) closely enough
/// to show the same screens; the real wording comes from the backend.
enum DelegatedDemo {
    static let pauseLine = "One moment, please."
    static let callbackLine = "I'll need to check that and call back. Thank you."
    static let closeLine = "Thank you for your help. Goodbye."
    static let offer = "We have 10:30 tomorrow morning. Does that work?"
    static let proposal = "10:30 tomorrow"
    static let confirmation = "Great, you're booked for 10:30 tomorrow morning."
    static let declined = "Then please call back when you know a better time."
    static let askTimeout = 10.0
    /// Version B: the receptionist asks "when?" without offering a time.
    static let openQuestion = "What time would you like to come in?"
    static let waitLine = "One moment, please, I'm checking."

    private static let days: [Sign: String] = [.today: "today", .now: "today", .tomorrow: "tomorrow", .yesterday: "yesterday"]
    private static let parts: [Sign: String] = [
        .morning: "in the morning", .afternoon: "in the afternoon", .evening: "in the evening", .night: "at night",
    ]

    static func goal(_ purpose: CallPurpose) -> String {
        switch purpose {
        case .doctorAppointment: "book a doctor's appointment"
        }
    }

    /// When the user wants it, from the time chips: "tomorrow in the morning".
    static func when(_ chips: [Sign]) -> String? {
        let words = chips.compactMap { days[$0] } + chips.compactMap { parts[$0] }
        let unique = words.reduce(into: [String]()) { if !$0.contains($1) { $0.append($1) } }
        return unique.isEmpty ? nil : unique.joined(separator: " ")
    }

    static func brief(for request: BriefRequest) -> Brief {
        let goal = goal(request.purpose)
        let name = request.profile.name.trimmingCharacters(in: .whitespaces)
        let when = when(request.chips)
        var lines = ["Call on behalf of \(name), who is Deaf and uses the Ishara app, to \(goal)."]
        if let when { lines.append("Preferred: \(when).") }
        if let notes = request.profile.notes, !notes.isEmpty { lines.append("Reason, if asked: \(notes)") }
        let share = ["name (\(name))"] + (request.profile.callback == nil ? [] : ["callback number"])
        lines.append("May share: \(share.joined(separator: ", ")).")
        lines.append("Will not agree to anything outside this brief; anything else comes back to you as a question.")
        return Brief(
            briefID: "demo-brief", text: lines.joined(separator: " "), goal: goal,
            constraints: when.map { ["preferred time: \($0)"] } ?? [])
    }

    static func opening(name: String, goal: String, when: String?) -> String {
        "I'd like to \(goal) for \(name)" + (when.map { ", \($0)." } ?? ".")
    }

    static let options: [AskOption] = [
        AskOption(choice: .yes, spoken: "Yes, \(proposal) works. Thank you."),
        AskOption(choice: .no, spoken: "No, \(proposal) doesn't work, sorry. Is there another time?"),
        AskOption(choice: .wait, spoken: waitLine),
    ]

    /// The answer to an open "when?", like the backend's `_time_line`.
    static func timeLine(_ when: String) -> String {
        when.prefix(1).uppercased() + when.dropFirst() + ", please. What times are available?"
    }

    /// The time words the user can sign or tap for an open "when?" (backend `TIME_OPTIONS`).
    static let timeOptions: [AskOption] = [
        AskOption(choice: .tomorrow, spoken: timeLine("tomorrow")),
        AskOption(choice: .morning, spoken: timeLine("in the morning")),
        AskOption(choice: .now, spoken: timeLine("today, as soon as possible")),
        AskOption(choice: .wait, spoken: waitLine),
    ]

    /// Notes from the transcript, quoting it, like the backend's deterministic notes.
    static func notes(goal: String, name: String, brief: String, transcript: [TranscriptEntry], answers: [String], ready: Bool) -> CallNotes {
        var summary = ["Goal: \(goal) for \(name)."]
        let receptionist = transcript.filter { $0.speaker == .receptionist }.map(\.text)
        if receptionist.contains(offer) { summary.append("They offered: \"\(offer)\"") }
        summary += answers.map { "You answered: \"\($0)\"" }
        if receptionist.contains(confirmation) { summary.append("They confirmed: \"\(confirmation)\"") }
        var outcome: String?
        var open: [String] = []
        if ready {
            if receptionist.contains(confirmation) {
                outcome = "booked"
            } else if transcript.contains(where: { $0.speaker == .agent && $0.text == callbackLine }) {
                outcome = "callback"
                open.append("The agent promised to call back. Decide on the offer and call again.")
            } else if answers.contains(where: { $0.hasPrefix("No") }) {
                outcome = "declined"
            } else {
                outcome = "unclear"
                open.append("Nothing was confirmed. Read the transcript and decide the next step.")
            }
        }
        return CallNotes(
            callID: "demo-call", mode: .delegated, ready: ready, brief: brief, outcome: outcome,
            summary: summary, openQuestions: open, transcript: transcript, bolnaSummary: nil)
    }
}
