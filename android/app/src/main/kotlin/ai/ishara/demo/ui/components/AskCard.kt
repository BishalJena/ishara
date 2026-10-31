package ai.ishara.demo.ui.components

import ai.ishara.demo.core.call.AskChoice
import ai.ishara.demo.core.call.AskOption
import ai.ishara.demo.core.call.OpenQuestion
import ai.ishara.demo.ui.theme.IsharaColors
import ai.ishara.demo.ui.theme.IsharaType
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicText
import androidx.compose.foundation.text.TextAutoSize
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Info
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.math.max

/**
 * Decision D9, attended delegated call: the agent said "one moment, please" and needs the
 * user's answer: YES / NO / WAIT for an offered time, or a time word and WAIT for an open
 * "when?". Each button shows exactly what the agent will say; signing an option's word answers
 * too. Nothing is spoken until one is chosen (or the backend's timeout line after [OpenQuestion.timeoutS]).
 *
 * The user is asked to sign the answer, so the card leaves the camera in view above it: the
 * answers sit two per row with their sentences in small type and the question shows at most two
 * lines (TalkBack reads all of it). Above XL text the sentences no longer fit in the buttons, so
 * the question and each option's exact sentence scroll in a bounded box ([maxHeight] at the
 * large standard sizes, [detailsMaxHeight] at accessibility sizes) and short option-word buttons
 * stay below it, never scrolled away (the answer has a 10 s timeout).
 */
@Composable
fun AskCard(
    question: OpenQuestion,
    onAnswer: (AskChoice) -> Unit,
    modifier: Modifier = Modifier,
    detailsMaxHeight: Dp = 240.dp,
    maxHeight: Dp? = null,
) {
    var shortAnswersHeight by remember { mutableStateOf<Dp?>(null) }
    val isAccessibilitySize = isAccessibilityTextSize()
    val isLarge = isLargerThanExtraLargeText()
    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(IsharaColors.Orange.copy(alpha = 0.12f), RoundedCornerShape(16.dp))
            .padding(CARD_PADDING),
    ) {
        when {
            isAccessibilitySize -> CompactAsk(question, onAnswer, detailsMaxHeight) { shortAnswersHeight = it }
            isLarge -> {
                val sentencesMax = maxHeight?.let { cardMax ->
                    max(60f, (cardMax - CARD_PADDING * 2 - (shortAnswersHeight ?: 0.dp) - COMPACT_SPACING).value).dp
                } ?: detailsMaxHeight
                CompactAsk(question, onAnswer, sentencesMax) { shortAnswersHeight = it }
            }
            else -> RegularAsk(question, onAnswer)
        }
    }
}

private val CARD_PADDING = 12.dp
private val COMPACT_SPACING = 10.dp

@Composable
private fun RegularAsk(question: OpenQuestion, onAnswer: (AskChoice) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        AskHeader()
        QuestionText(question, maxLines = 2)
        AnswerGrid(question.options) { option, cellModifier ->
            AnswerButton(option, onAnswer, cellModifier) {
                Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    OptionWord(option)
                    Text(option.spoken, style = IsharaType.caption)
                }
            }
        }
        Text(askFallbackText(question), style = IsharaType.caption, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun CompactAsk(question: OpenQuestion, onAnswer: (AskChoice) -> Unit, detailsMaxHeight: Dp, onAnswersHeight: (Dp) -> Unit) {
    val density = LocalDensity.current
    Column(verticalArrangement = Arrangement.spacedBy(COMPACT_SPACING)) {
        PinnedSentence(maxHeight = detailsMaxHeight) {
            Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                AskHeader()
                QuestionText(question, maxLines = Int.MAX_VALUE)
                question.options.forEach { option ->
                    Text("${option.choice.name}: \u201C${option.spoken}\u201D", style = IsharaType.body)
                }
                Text(askFallbackText(question), style = IsharaType.footnote, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        val answersModifier = Modifier.onSizeChanged { onAnswersHeight(with(density) { it.height.toDp() }) }
        if (question.options.size > 3) {
            // Four answers (an open "when?") one per row push WAIT off screen: two per row.
            Column(answersModifier) {
                AnswerGrid(question.options) { option, cellModifier -> ShortAnswerButton(option, onAnswer, cellModifier) }
            }
        } else {
            Row(answersModifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                question.options.forEach { option -> ShortAnswerButton(option, onAnswer, Modifier.weight(1f)) }
            }
        }
    }
}

/** Two answers per row (TOMORROW · MORNING / NOW · WAIT, or YES · NO / WAIT); an odd last answer takes the whole row. */
@Composable
private fun AnswerGrid(options: List<AskOption>, cell: @Composable (AskOption, Modifier) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        options.chunked(2).forEach { row ->
            // Rows as tall as their tallest answer.
            Row(Modifier.fillMaxWidth().height(IntrinsicSize.Min), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                row.forEach { option -> cell(option, Modifier.weight(1f).fillMaxHeight()) }
            }
        }
    }
}

@Composable
private fun ShortAnswerButton(option: AskOption, onAnswer: (AskChoice) -> Unit, modifier: Modifier) {
    AnswerButton(option, onAnswer, modifier.heightIn(min = 52.dp)) {
        val color = if (option.choice == AskChoice.WAIT) IsharaColors.Gray else MaterialTheme.colorScheme.primary
        BasicText(
            option.choice.name,
            style = optionWordStyle.copy(color = color, textAlign = TextAlign.Center),
            maxLines = 1,
            autoSize = TextAutoSize.StepBased(minFontSize = 9.sp, maxFontSize = optionWordStyle.fontSize),
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

@Composable
private fun AskHeader() {
    IconLabel(
        "The agent is asking you",
        Icons.Filled.Info,
        color = IsharaColors.Orange,
        style = IsharaType.subheadline.copy(fontWeight = FontWeight.SemiBold),
    )
}

@Composable
private fun QuestionText(question: OpenQuestion, maxLines: Int) {
    Text(
        question.question,
        style = IsharaType.headline,
        maxLines = maxLines,
        overflow = TextOverflow.Ellipsis,
        modifier = Modifier.testTag("ask.question"),
    )
}

private val optionWordStyle = IsharaType.headline.copy(fontFamily = FontFamily.Monospace, fontWeight = FontWeight.Bold)

@Composable
private fun OptionWord(option: AskOption) {
    Text(option.choice.name, style = optionWordStyle)
}

fun askFallbackText(question: OpenQuestion): String =
    "No answer in ${question.timeoutS.toInt()} s: the agent says \u201C${question.fallback}\u201D"

@Composable
private fun AnswerButton(option: AskOption, onAnswer: (AskChoice) -> Unit, modifier: Modifier, content: @Composable () -> Unit) {
    val tint = if (option.choice == AskChoice.WAIT) IsharaColors.Gray else MaterialTheme.colorScheme.primary
    BorderedButton(
        onClick = { onAnswer(option.choice) },
        tint = tint,
        shape = RoundedCornerShape(12.dp),
        contentPadding = PaddingValues(horizontal = 12.dp, vertical = 8.dp),
        modifier = modifier.testTag("ask.${option.choice.name.lowercase()}"),
    ) {
        Column(Modifier.fillMaxHeight(), verticalArrangement = Arrangement.Top, horizontalAlignment = Alignment.Start) { content() }
    }
}
