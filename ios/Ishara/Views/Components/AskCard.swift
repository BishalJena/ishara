import CallSession
import SwiftUI

/// Decision D9, attended delegated call: the agent said "one moment, please" and needs the
/// user's answer: YES / NO / WAIT for an offered time, or a time word (TOMORROW, MORNING,
/// NOW) and WAIT for an open "when?". Each button shows exactly what the agent will say;
/// signing an option's word answers too. Nothing is spoken until one is chosen (or the
/// backend's timeout line).
///
/// At accessibility text sizes the question and the sentences no longer fit with their
/// buttons, and the answer has a 10 s timeout, so the buttons must never scroll away:
/// the question and each option's exact sentence scroll in a bounded box, and short
/// option-word buttons stay below it.
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
                            // Time words ("TOMORROW") are longer than YES / NO: never cut.
                            .fixedSize()
                            .frame(minWidth: 56, alignment: .leading)
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
            if question.options.count > 3 {
                // Four answers (an open "when?") stacked one per row push WAIT off screen:
                // two per row, the words shrinking to fit.
                Grid(horizontalSpacing: 10, verticalSpacing: 10) {
                    ForEach(Array(stride(from: 0, to: question.options.count, by: 2)), id: \.self) { start in
                        GridRow {
                            ForEach(question.options[start..<min(start + 2, question.options.count)], id: \.choice) {
                                shortButton($0)
                            }
                        }
                    }
                }
            } else {
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 10) { shortButtons }
                    VStack(spacing: 10) { shortButtons }
                }
            }
        }
    }

    private var shortButtons: some View {
        ForEach(question.options, id: \.choice) { shortButton($0) }
    }

    private func shortButton(_ option: AskOption) -> some View {
        answerButton(option) {
            Text(option.choice.rawValue.uppercased())
                .font(.headline.monospaced())
                .lineLimit(1)
                .minimumScaleFactor(0.5)
                .frame(maxWidth: .infinity)
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

#Preview("Open time question") {
    AskCard(
        question: OpenQuestion(
            askID: "t1", question: "What time would you like to come in?",
            options: [
                AskOption(choice: .tomorrow, spoken: "Tomorrow, please. What times are available?"),
                AskOption(choice: .morning, spoken: "In the morning, please. What times are available?"),
                AskOption(choice: .now, spoken: "Today, as soon as possible, please. What times are available?"),
                AskOption(choice: .wait, spoken: "One moment, please, I'm checking."),
            ],
            fallback: "I'll need to check that and call back. Thank you.", timeoutS: 10, askedAt: Date()),
        onAnswer: { _ in }
    )
    .padding()
}
