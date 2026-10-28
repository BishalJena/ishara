import CallSession
import SwiftUI

/// Decision D9, attended delegated call: the agent said "one moment, please" and needs the
/// user's answer: YES / NO / WAIT for an offered time, or a time word (TOMORROW, MORNING,
/// NOW) and WAIT for an open "when?". Each button shows exactly what the agent will say;
/// signing an option's word answers too. Nothing is spoken until one is chosen (or the
/// backend's timeout line).
///
/// The user is asked to sign the answer, so the card must leave the camera in view above
/// it: the answers sit two per row with their sentences in small type, and the question
/// shows at most two lines (VoiceOver reads all of it), whatever the transcriber made of
/// the receptionist's words. Above XL text the sentences no longer fit in the buttons,
/// so the card takes the accessibility layout below, limited to `maxHeight`.
///
/// At accessibility text sizes the question and the sentences no longer fit with their
/// buttons, and the answer has a 10 s timeout, so the buttons must never scroll away:
/// the question and each option's exact sentence scroll in a bounded box, and short
/// option-word buttons stay below it.
struct AskCard: View {
    let question: OpenQuestion
    /// The tallest the scrolling question box may grow at accessibility text sizes.
    var detailsMaxHeight: CGFloat = 240
    /// The tallest the whole card may be at the large standard text sizes; nil for no limit.
    var maxHeight: CGFloat?
    let onAnswer: (AskChoice) -> Void

    @Environment(\.dynamicTypeSize) private var typeSize
    /// The short answer buttons, measured so the sentences get the rest of `maxHeight`.
    @State private var shortAnswersHeight: CGFloat?

    private static let padding: CGFloat = 12
    private static let compactSpacing: CGFloat = 10

    var body: some View {
        Group {
            if typeSize.isAccessibilitySize {
                compact(detailsMaxHeight: detailsMaxHeight)
            } else if typeSize > .xLarge {
                compact(detailsMaxHeight: maxHeight.map(sentencesMaxHeight(cardMaxHeight:)) ?? detailsMaxHeight)
            } else {
                regular
            }
        }
        .padding(Self.padding)
        .background(.orange.opacity(0.12), in: RoundedRectangle(cornerRadius: 16))
    }

    private func sentencesMaxHeight(cardMaxHeight: CGFloat) -> CGFloat {
        let answers = (shortAnswersHeight ?? 0) + Self.compactSpacing
        return max(60, cardMaxHeight - 2 * Self.padding - answers)
    }

    private var regular: some View {
        VStack(alignment: .leading, spacing: 6) {
            header
            questionText
                .lineLimit(2)
            answerGrid { option in
                answerButton(option) {
                    VStack(alignment: .leading, spacing: 2) {
                        optionWord(option)
                        Text(option.spoken)
                            .font(.caption)
                            .multilineTextAlignment(.leading)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                }
            }
            fallbackText(font: .caption)
        }
    }

    private func compact(detailsMaxHeight: CGFloat) -> some View {
        VStack(alignment: .leading, spacing: Self.compactSpacing) {
            PinnedSentence(maxHeight: detailsMaxHeight) {
                VStack(alignment: .leading, spacing: 10) {
                    header
                    questionText
                    ForEach(question.options, id: \.choice) { option in
                        Text("\(option.choice.rawValue.uppercased()): \u{201C}\(option.spoken)\u{201D}")
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    fallbackText(font: .footnote)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            Group {
                if question.options.count > 3 {
                    // Four answers (an open "when?") stacked one per row push WAIT off screen:
                    // two per row, the words shrinking to fit.
                    answerGrid(shortButton)
                } else {
                    ViewThatFits(in: .horizontal) {
                        HStack(spacing: 10) { shortButtons }
                        VStack(spacing: 10) { shortButtons }
                    }
                }
            }
            .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { shortAnswersHeight = $0 }
        }
    }

    /// Two answers per row (TOMORROW · MORNING / NOW · WAIT, or YES · NO / WAIT); an odd
    /// last answer takes the whole row.
    private func answerGrid<Cell: View>(@ViewBuilder _ button: @escaping (AskOption) -> Cell) -> some View {
        let options = question.options
        return Grid(horizontalSpacing: 8, verticalSpacing: 6) {
            ForEach(Array(stride(from: 0, to: options.count, by: 2)), id: \.self) { start in
                GridRow {
                    if start + 1 < options.count {
                        button(options[start])
                        button(options[start + 1])
                    } else {
                        button(options[start]).gridCellColumns(2)
                    }
                }
            }
        }
        // Rows as tall as their tallest answer, not as tall as the bar allows.
        .fixedSize(horizontal: false, vertical: true)
    }

    private var shortButtons: some View {
        ForEach(question.options, id: \.choice) { shortButton($0) }
    }

    private func shortButton(_ option: AskOption) -> some View {
        answerButton(option, size: .large) {
            optionWord(option)
                .lineLimit(1)
                .minimumScaleFactor(0.5)
                .frame(maxWidth: .infinity)
        }
    }

    private func optionWord(_ option: AskOption) -> some View {
        Text(option.choice.rawValue.uppercased())
            .font(.headline.monospaced())
    }

    private var header: some View {
        Label("The agent is asking you", systemImage: "questionmark.bubble.fill")
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(.orange)
    }

    private var questionText: some View {
        Text(question.question)
            .font(.headline)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("ask.question")
    }

    private func fallbackText(font: Font) -> some View {
        Text("No answer in \(Int(question.timeoutS)) s: the agent says \u{201C}\(question.fallback)\u{201D}")
            .font(font)
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
    }

    private func answerButton(_ option: AskOption, size: ControlSize = .regular,
                              @ViewBuilder label: () -> some View) -> some View {
        Button(action: { onAnswer(option.choice) }, label: label)
            .buttonStyle(.bordered)
            .buttonBorderShape(.roundedRectangle(radius: 12))
            .controlSize(size)
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
            askID: "t1", question: "what time would will would you like to come in",
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
