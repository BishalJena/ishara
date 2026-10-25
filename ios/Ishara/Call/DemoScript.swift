import CallSession
import Foundation

/// The rehearsed clinic call from PLAN §1, used by `FakeCallDriver`.
enum DemoScript {
    struct Stage: Sendable {
        /// What the receptionist says before the user replies (nil for the opening turn).
        let caption: String?
        /// Show the red "can't see you" pill briefly before signing.
        let losesFraming: Bool
        /// What the sign pipeline reports, in order.
        let signs: [RecognitionResult]
    }

    /// The call agent's fixed lines, said without a SEND (backend/app/markers.py).
    static let disclosure = "Hello, I'm calling for a Deaf caller who is using Ishara, a sign-language app. "
        + "Their replies may take a few seconds."
    static let goodbye = "Thank you for your time. Goodbye."

    static let stages: [Stage] = [
        // Turn 1: hello · doctor · tomorrow
        Stage(caption: nil, losesFraming: false,
              signs: [.sign(.hello), .sign(.doctor), .sign(.tomorrow)]),
        // Turns 2–3b: "afternoon" is the planned wrong chip the user removes with ✕.
        Stage(caption: "We have 4 pm tomorrow. Does that work?", losesFraming: true,
              signs: [.sign(.no), .sign(.afternoon), .sign(.morning)]),
        // Turns 4–5: one unsure sign shows a red [?] chip that is never sent.
        Stage(caption: "Yes, 10:30 tomorrow morning.", losesFraming: false,
              signs: [.sign(.yes), .unsure, .sign(.thankyou)]),
    ]

    /// Drafts the composer would return for the script's chip sets.
    static let composedDrafts: [[Sign]: String] = [
        [.hello, .doctor, .tomorrow]: "Hello, I'd like a doctor's appointment tomorrow.",
        [.no, .morning]: "No, sorry, 4 pm doesn't work. Is there anything tomorrow morning?",
        [.yes, .thankyou]: "Yes, 10:30 tomorrow morning works. Thank you.",
    ]

    /// Fixed fallback phrase per sign, joined in order, like the backend templates.
    static let templatePhrases: [Sign: String] = [
        .hello: "Hello.",
        .thankyou: "Thank you.",
        .yes: "Yes.",
        .no: "No.",
        .sorry: "Sorry.",
        .doctor: "I'd like to see a doctor.",
        .today: "Today, please.",
        .tomorrow: "Tomorrow, please.",
        .morning: "In the morning, please.",
        .afternoon: "In the afternoon, please.",
        .evening: "In the evening, please.",
        .time: "What time?",
        // ASL Signs glosses (D8), said plainly like backend/app/templates.py.
        .please: "Please.",
        .now: "Today, please.",
        .wait: "A moment, please.",
        .night: "At night, please.",
        .yesterday: "Yesterday.",
        .later: "Maybe later.",
        .can: "Can you help me with that?",
        .where: "Where is it?",
        .who: "Who should I ask for?",
        .why: "Why is that?",
        .have: "Do you have that?",
        .finish: "That's all from me.",
        .callonphone: "Please call me on the phone.",
        .sick: "I'm feeling sick.",
        .hungry: "I'm hungry.",
        .drink: "I'd like a drink.",
        .water: "Some water, please.",
        .home: "At home.",
        .go: "I need to go.",
        .see: "I'd like to see them.",
        .hear: "I hear you.",
        .read: "I'll read it.",
    ]

    /// LLM wording when the chips match a scripted turn, otherwise the template.
    static func draft(for signs: [Sign]) -> (text: String, source: DraftSource) {
        if let text = composedDrafts[signs] {
            return (text, .llm)
        }
        let text = signs.map { templatePhrases[$0] ?? "\($0.rawValue.capitalized)." }.joined(separator: " ")
        return (text, .template)
    }
}
