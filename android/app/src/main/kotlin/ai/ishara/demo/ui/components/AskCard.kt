package ai.ishara.demo.ui.components

import ai.ishara.demo.core.call.AskChoice
import ai.ishara.demo.core.call.AskOption
import ai.ishara.demo.core.call.OpenQuestion
import ai.ishara.demo.ui.theme.IsharaColors
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp

/**
 * Decision D9, attended delegated call: the agent said "one moment, please" and needs the
 * user's answer: YES / NO / WAIT for an offered time, or a time word and WAIT for an open
 * "when?". Each button shows exactly what the agent will say; signing an option's word answers
 * too. Nothing is spoken until one is chosen (or the backend's timeout line after [OpenQuestion.timeoutS]).
 * Answers sit two per row and the question shows at most two lines, so the camera stays in view.
 */
@Composable
fun AskCard(question: OpenQuestion, onAnswer: (AskChoice) -> Unit, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(IsharaColors.Orange.copy(alpha = 0.12f), RoundedCornerShape(16.dp))
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Text(
            "The agent is asking you",
            style = MaterialTheme.typography.titleSmall,
            color = IsharaColors.Orange,
        )
        Text(
            question.question,
            style = MaterialTheme.typography.titleMedium,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.testTag("ask.question"),
        )
        // Two answers per row; an odd last answer takes the whole row.
        question.options.chunked(2).forEach { row ->
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                row.forEach { option -> AnswerButton(option, onAnswer, Modifier.weight(1f)) }
            }
        }
        Text(
            askFallbackText(question),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

fun askFallbackText(question: OpenQuestion): String =
    "No answer in ${question.timeoutS.toInt()} s: the agent says \u201C${question.fallback}\u201D"

@Composable
private fun AnswerButton(option: AskOption, onAnswer: (AskChoice) -> Unit, modifier: Modifier) {
    val word = option.choice.name
    OutlinedButton(
        onClick = { onAnswer(option.choice) },
        shape = RoundedCornerShape(12.dp),
        colors = ButtonDefaults.outlinedButtonColors(
            contentColor = if (option.choice == AskChoice.WAIT) IsharaColors.Gray else MaterialTheme.colorScheme.primary,
        ),
        modifier = modifier
            .testTag("ask.${word.lowercase()}")
            .semantics { stateDescription = "The agent says \u201C${option.spoken}\u201D" },
    ) {
        Column(modifier = Modifier.fillMaxWidth()) {
            Text(word, style = MaterialTheme.typography.titleMedium.copy(fontFamily = FontFamily.Monospace, fontWeight = FontWeight.Bold))
            Spacer(Modifier.padding(1.dp))
            Text(option.spoken, style = MaterialTheme.typography.bodySmall)
        }
    }
}
