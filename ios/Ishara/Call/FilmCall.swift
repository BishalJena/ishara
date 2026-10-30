import CallSession
import Foundation

/// The call in the launch film (docs/demo/video/SCRIPT.md §5), played by `FakeCallDriver`
/// with `-IsharaFilm 1`: City Care Clinic, a receptionist called Priya, and the lines Ishara
/// says under the steer rules. Everyone and everything in it is fictional. Each line is
/// paced by how long it takes to say, so the film's voices can be laid on exactly.
enum FilmCall {
    static let greeting = "Good morning, City Care Clinic, Priya speaking."
    static let request = "Book a follow-up with Dr. Kavita Rao for my blood pressure, this week, mornings if possible."

    static func opening(name: String) -> String {
        "I'm calling on behalf of \(name). They'd like to book a follow-up with Dr. Kavita Rao for their blood pressure, this week, mornings if possible."
    }

    /// The receptionist's turns, each with what Ishara proposes in reply (nil: nothing).
    static let turns: [(heard: String, reply: String?)] = [
        ("Of course. Is Aarav already registered with us?",
         "Yes, they are. Their patient ID is CCC-20417."),
        ("Thank you. Dr. Rao's earliest is Wednesday at 4 pm.",
         "Sorry, 4 pm doesn't work for them. Is there anything in the morning?"),
        ("Let me see. I have Thursday at 10:30 am.",
         "Yes, Thursday at 10:30 works. Thank you."),
        ("Lovely. Any allergies or regular medicines Dr. Rao should know about?",
         "They're allergic to penicillin, and they take amlodipine 5 mg once a day."),
        ("Noted. You're booked for Thursday at 10:30 with Dr. Rao. Please bring your recent reports.",
         "That's all, thank you so much for your help."),
        ("You're welcome, Aarav. See you on Thursday!", nil),
    ]

    /// The step whose receptionist line confirms the booking.
    static let bookedTurn = 4

    /// How the backend's polish (Groq) rewords the film's one-tap reply.
    static func polished(_ typed: String) -> String? {
        typed.hasPrefix("Yes, 10:30") ? "Yes, Thursday at 10:30 works perfectly." : nil
    }

    /// What the composer drafts from the film's signed THANK YOU.
    static func signedDraft(for signs: [Sign]) -> String? {
        signs == [.thankyou] ? "Thank you so much for your help." : nil
    }

    /// Where the film's timeline goes: one JSON object per line, with the wall-clock time each
    /// line was said or each state was reached, to lay the voices on the screen recording.
    static let timelineURL = FileManager.default.temporaryDirectory.appendingPathComponent("film-timeline.jsonl")

    static func log(_ message: ServerMessage) {
        let event: [String: Any]? = switch message {
        case let .caption(text, _, speaker): ["kind": "caption", "speaker": "\(speaker)", "text": text]
        case let .proposal(_, text, windowS, origin): ["kind": "proposal", "origin": "\(origin)", "text": text, "window": windowS]
        case let .proposalResolved(_, outcome): ["kind": "resolved", "outcome": "\(outcome)"]
        case let .status(state): ["kind": "status", "state": "\(state)"]
        case let .draft(_, text, _): ["kind": "draft", "text": text]
        case .spoken: ["kind": "spoken"]
        default: nil
        }
        guard var event else { return }
        event["t"] = Date().timeIntervalSince1970
        guard let data = try? JSONSerialization.data(withJSONObject: event), var line = String(data: data, encoding: .utf8) else { return }
        line += "\n"
        if let handle = try? FileHandle(forWritingTo: timelineURL) {
            handle.seekToEndOfFile()
            handle.write(Data(line.utf8))
            try? handle.close()
        } else {
            try? Data(line.utf8).write(to: timelineURL)
        }
    }

    /// Seconds to say `text` at a calm phone pace (about 15 characters a second).
    static func speech(_ text: String) -> Double {
        max(1.2, Double(text.count) / 15)
    }

    static func notes(name: String, ready: Bool, transcript: [TranscriptEntry], userLines: [String], steppedIn: Int) -> CallNotes {
        var summary = [
            "You asked: \"\(request)\"",
            "They offered: \"Dr. Rao's earliest is Wednesday at 4 pm.\"",
            "Ishara answered: \"\(turns[1].reply ?? "")\"",
            "They offered: \"I have Thursday at 10:30 am.\"",
        ]
        summary += userLines.map { "You answered: \"\($0)\"" }
        summary.append("Ishara shared from Health history.pdf: \"\(turns[3].reply ?? "")\"")
        summary.append("They confirmed: \"You're booked for Thursday at 10:30 with Dr. Rao. Please bring your recent reports.\"")
        var notes = CallNotes(callID: "film-call", mode: .steer, ready: ready, transcript: transcript)
        notes.brief = opening(name: name)
        notes.outcome = ready ? "booked" : nil
        notes.summary = ready ? summary : []
        notes.steppedIn = steppedIn
        return notes
    }
}
