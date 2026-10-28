import CallSession
import SwiftUI

/// Decision D9, attended delegated call: the agent said "one moment, please" and needs the
/// user's answer. Each button shows exactly what the agent will say; signing yes / no / wait
/// answers too. Nothing is spoken until one is chosen (or the backend's timeout line).
///
/// At accessibility text sizes the question and the three sentences no longer fit with
/// their buttons, and the answer has a 10 s timeout, so the buttons must never scroll away:
/// the question and each option's exact sentence scroll in a bounded box, and short
/// YES / NO / WAIT buttons stay below it.
struct AskCard: View {
    let question: OpenQuestion
    /// The tallest the scrolling question box may grow at accessibility text sizes.
    var detailsMaxHeight: CGFloat = 240
    let onAnswer: (AskChoice) -> Void

    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        Group {
            if typeSize.isAccessibilitySize {
                compact
            } else {
                regular
            }
        }
        .padding()
        .background(.orange.opacity(0.12), in: RoundedRectangle(cornerRadius: 16))
    }

    private var regular: some View {
        VStack(alignment: .leading, spacing: 10) {
            header
            questionText
            ForEach(question.options, id: \.choice) { option in
                answerButton(option) {
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
            }
            fallbackText
        }
    }

    private var compact: some View {
        VStack(alignment: .leading, spacing: 10) {
            PinnedSentence(maxHeight: detailsMaxHeight) {
                VStack(alignment: .leading, spacing: 10) {
                    header
                    questionText
                    ForEach(question.options, id: \.choice) { option in
                        Text("\(option.choice.rawValue.uppercased()): \u{201C}\(option.spoken)\u{201D}")
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    fallbackText
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 10) { shortButtons }
                VStack(spacing: 10) { shortButtons }
            }
        }
    }

    private var shortButtons: some View {
        ForEach(question.options, id: \.choice) { option in
            answerButton(option) {
                Text(option.choice.rawValue.uppercased())
                    .font(.headline.monospaced())
                    .lineLimit(1)
                    .frame(maxWidth: .infinity)
            }
        }
    }

    private var header: some View {
        Label("The agent is asking you", systemImage: "questionmark.bubble.fill")
            .font(.headline)
            .foregroundStyle(.orange)
    }

    private var questionText: some View {
        Text(question.question)
            .font(.title3.weight(.semibold))
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("ask.question")
    }

    private var fallbackText: some View {
        Text("No answer in \(Int(question.timeoutS)) s: the agent says \u{201C}\(question.fallback)\u{201D}")
            .font(.footnote)
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
    }

    private func answerButton(_ option: AskOption, @ViewBuilder label: () -> some View) -> some View {
        Button(action: { onAnswer(option.choice) }, label: label)
            .buttonStyle(.bordered)
            .controlSize(.large)
            .tint(option.choice == .wait ? .gray : .accentColor)
            .accessibilityIdentifier("ask.\(option.choice.rawValue)")
            .accessibilityHint("The agent says \u{201C}\(option.spoken)\u{201D}")
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
