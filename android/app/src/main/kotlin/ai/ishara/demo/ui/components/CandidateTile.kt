package ai.ishara.demo.ui.components

import ai.ishara.demo.core.call.Sign
import ai.ishara.demo.ui.theme.IsharaColors
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
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
    Row(modifier = modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        OutlinedButton(
            onClick = onAccept,
            colors = ButtonDefaults.outlinedButtonColors(contentColor = IsharaColors.Green),
            modifier = Modifier
                .weight(1f)
                .testTag("candidate.accept")
                .semantics { contentDescription = "Did you mean ${sign.wire}? Double tap to use it." },
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                Text(
                    buildAnnotatedString {
                        append("Did you mean ")
                        withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append(sign.wire.uppercase()) }
                        append("?")
                    },
                )
                Spacer(Modifier.weight(1f))
                Text("Use it", style = MaterialTheme.typography.labelLarge)
            }
        }
        OutlinedButton(
            onClick = onDismiss,
            modifier = Modifier.testTag("candidate.dismiss").semantics { contentDescription = "No, sign again" },
        ) { Text("✕") }
    }
}

/** Shown after a `?` that happened because a hand left the picture during the sign. */
@Composable
fun FramingHint(modifier: Modifier = Modifier) {
    Text(
        "A hand left the picture. Keep both hands inside the frame and sign again.",
        style = MaterialTheme.typography.bodyMedium,
        color = IsharaColors.Orange,
        modifier = modifier.fillMaxWidth().testTag("call.framingHint"),
    )
}
