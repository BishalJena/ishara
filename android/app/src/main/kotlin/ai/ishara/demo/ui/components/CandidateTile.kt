package ai.ishara.demo.ui.components

import ai.ishara.demo.core.call.Sign
import ai.ishara.demo.models.wire
import ai.ishara.demo.ui.theme.IsharaColors
import ai.ishara.demo.ui.theme.IsharaType
import androidx.compose.foundation.layout.Arrangement
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
    Row(modifier = modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        BorderedButton(
            onClick = onAccept,
            tint = IsharaColors.Green,
            shape = shape,
            contentPadding = padding,
            modifier = Modifier
                .weight(1f)
                .heightIn(min = 50.dp)
                .testTag("candidate.accept")
                .semantics { contentDescription = "Did you mean ${sign.wire}? Double tap to use it." },
        ) {
            Text(
                buildAnnotatedString {
                    append("Did you mean ")
                    withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append(sign.wire.uppercase()) }
                    append("?")
                },
                style = IsharaType.body,
                color = MaterialTheme.colorScheme.onSurface,
            )
            Spacer(Modifier.weight(1f))
            Text("Use it", style = IsharaType.subheadline.copy(fontWeight = FontWeight.SemiBold))
        }
        BorderedButton(
            onClick = onDismiss,
            tint = MaterialTheme.colorScheme.primary,
            shape = shape,
            contentPadding = padding,
            modifier = Modifier.heightIn(min = 50.dp).testTag("candidate.dismiss").semantics { contentDescription = "No, sign again" },
        ) { Icon(Icons.Filled.Close, contentDescription = null, modifier = Modifier.size(20.dp)) }
    }
}

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
