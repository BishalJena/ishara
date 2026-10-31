package ai.ishara.demo.ui.components

import ai.ishara.demo.core.call.Sign
import ai.ishara.demo.models.wire
import ai.ishara.demo.ui.theme.IsharaColors
import ai.ishara.demo.ui.theme.IsharaType
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp

/**
 * Decision D8 pick-one: the model is fairly but not fully sure of a sign. It becomes a chip
 * (or answers the agent's question) only if the user taps it; nothing is spoken by itself.
 */
@Composable
fun CandidateTile(sign: Sign, onAccept: () -> Unit, onDismiss: () -> Unit, modifier: Modifier = Modifier) {
    val shape = RoundedCornerShape(12.dp)
    val padding = PaddingValues(horizontal = 16.dp, vertical = 12.dp)
    BoxWithConstraints(modifier.fillMaxWidth()) {
        // Beside the signing video there is no room for the question and "Use it" on one line,
        // and at accessibility text sizes none for ✕ beside them either.
        val isNarrow = maxWidth < NARROW_WIDTH
        val stacksDismiss = isNarrow && isAccessibilityTextSize()
        val accept = @Composable { buttonModifier: Modifier ->
            BorderedButton(
                onClick = onAccept,
                tint = IsharaColors.Green,
                shape = shape,
                contentPadding = padding,
                modifier = buttonModifier
                    .heightIn(min = 50.dp)
                    .testTag("candidate.accept")
                    .semantics { contentDescription = "Did you mean ${sign.wire}? Double tap to use it." },
            ) {
                val question = buildAnnotatedString {
                    append("Did you mean ")
                    withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append(sign.wire.uppercase()) }
                    append("?")
                }
                val useIt = @Composable { Text("Use it", style = IsharaType.subheadline.copy(fontWeight = FontWeight.SemiBold)) }
                if (isNarrow) {
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(question, style = IsharaType.body, color = MaterialTheme.colorScheme.onSurface)
                        useIt()
                    }
                } else {
                    Text(question, style = IsharaType.body, color = MaterialTheme.colorScheme.onSurface)
                    Spacer(Modifier.weight(1f))
                    useIt()
                }
            }
        }
        val dismiss = @Composable { buttonModifier: Modifier ->
            BorderedButton(
                onClick = onDismiss,
                tint = MaterialTheme.colorScheme.primary,
                shape = shape,
                contentPadding = padding,
                modifier = buttonModifier.heightIn(min = 50.dp).testTag("candidate.dismiss").semantics { contentDescription = "No, sign again" },
            ) { Icon(Icons.Filled.Close, contentDescription = null, modifier = Modifier.size(20.dp)) }
        }
        if (stacksDismiss) {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                accept(Modifier.fillMaxWidth())
                dismiss(Modifier.fillMaxWidth())
            }
        } else {
            Row(Modifier.height(IntrinsicSize.Min), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                accept(Modifier.weight(1f))
                dismiss(Modifier.fillMaxHeight())
            }
        }
    }
}

private val NARROW_WIDTH = 300.dp

/** Shown after a `?` that happened because a hand left the picture during the sign. */
@Composable
fun FramingHint(modifier: Modifier = Modifier) {
    IconLabel(
        "A hand left the picture. Keep both hands inside the frame and sign again.",
        Icons.Filled.Warning,
        modifier = modifier.fillMaxWidth().semantics(mergeDescendants = true) {}.testTag("call.framingHint"),
        color = IsharaColors.Orange,
        style = IsharaType.subheadline,
    )
}
