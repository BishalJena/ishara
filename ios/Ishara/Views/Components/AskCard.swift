import CallSession
import SwiftUI

/// Decision D9, attended delegated call: the agent said "one moment, please" and needs the
/// user's answer. Each button shows exactly what the agent will say; signing yes / no / wait
/// answers too. Nothing is spoken until one is chosen (or the backend's timeout line).
struct AskCard: View {
    let question: OpenQuestion
    let onAnswer: (AskChoice) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("The agent is asking you", systemImage: "questionmark.bubble.fill")
                .font(.headline)
                .foregroundStyle(.orange)
            Text(question.question)
                .font(.title3.weight(.semibold))
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("ask.question")
            ForEach(question.options, id: \.choice) { option in
                Button { onAnswer(option.choice) } label: {
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text(option.choice.rawValue.uppercased())
                            .font(.headline.monospaced())
                            .frame(width: 56, alignment: .leading)
                        Text(option.spoken)
                            .multilineTextAlignment(.leading)
                            .fixedSize(horizontal: false, vertical: true)
                        Spacer(minLength: 0)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .buttonStyle(.bordered)
                .controlSize(.large)
                .tint(option.choice == .wait ? .gray : .accentColor)
                .accessibilityIdentifier("ask.\(option.choice.rawValue)")
                .accessibilityHint("The agent says \u{201C}\(option.spoken)\u{201D}")
            }
            Text("No answer in \(Int(question.timeoutS)) s: the agent says \u{201C}\(question.fallback)\u{201D}")
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
        .padding()
        .background(.orange.opacity(0.12), in: RoundedRectangle(cornerRadius: 16))
    }
}

#Preview {
    AskCard(
        question: OpenQuestion(
            askID: "a1", question: "We have 4 pm tomorrow. Does that work?",
            options: [
                AskOption(choice: .yes, spoken: "Yes, 4 pm tomorrow works. Thank you."),
                AskOption(choice: .no, spoken: "No, 4 pm tomorrow doesn't work, sorry. Is there another time?"),
                AskOption(choice: .wait, spoken: "One moment, please, I'm checking."),
            ],
            fallback: "I'll need to check that and call back. Thank you.", timeoutS: 10, askedAt: Date()),
        onAnswer: { _ in }
    )
    .padding()
}
