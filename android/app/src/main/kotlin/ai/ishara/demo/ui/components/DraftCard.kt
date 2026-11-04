package ai.ishara.demo.ui.components

import ai.ishara.demo.core.call.QuickReply
import ai.ishara.demo.models.DraftBadge
import ai.ishara.demo.models.DraftDisplay
import ai.ishara.demo.models.label
import ai.ishara.demo.models.wire
import ai.ishara.demo.ui.theme.IsharaColors
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp

/** The sentence that SEND would speak, with a badge saying who wrote it. */
@Composable
fun DraftCard(draft: DraftDisplay?, modifier: Modifier = Modifier, isComposing: Boolean = false) {
    val description = when {
        draft != null -> "Draft from ${draft.badge.title}: ${draft.text}"
        isComposing -> "Composing the draft"
        else -> "No draft yet"
    }
    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(16.dp))
            .padding(16.dp)
            .semantics(mergeDescendants = true) { contentDescription = description }
            .testTag("call.draft"),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                "Draft",
                style = MaterialTheme.typography.titleSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.weight(1f))
            if (draft != null) SourceBadge(draft.badge)
        }
        when {
            draft != null -> Text("\u201C${draft.text}\u201D", style = MaterialTheme.typography.titleLarge)
            isComposing -> Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                Text("Composing…", color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            else -> Text("Sign your reply or pick a quick reply.", color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
fun SourceBadge(badge: DraftBadge) {
    val color = when (badge) {
        DraftBadge.LLM -> IsharaColors.Purple
        DraftBadge.TEMPLATE -> IsharaColors.Blue
        DraftBadge.QUICK_REPLY -> IsharaColors.Teal
        DraftBadge.NOT_DELIVERED -> IsharaColors.Orange
        DraftBadge.STOPPED -> IsharaColors.Gray
    }
    Text(
        badge.title,
        color = Color.White,
        style = MaterialTheme.typography.labelMedium.copy(fontWeight = FontWeight.Bold),
        modifier = Modifier
            .background(color, CircleShape)
            .padding(horizontal = 8.dp, vertical = 3.dp)
            .testTag("call.draftBadge"),
    )
}

/** Yes / No / Wait / Repeat. Each puts a full sentence in the draft; SEND is still needed. */
@Composable
fun QuickReplyBar(onChoose: (QuickReply) -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true) {
    // Scrolls sideways at large text sizes rather than wrapping into a tall grid.
    Row(
        modifier = modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        QuickReply.entries.forEach { reply ->
            OutlinedButton(
                onClick = { onChoose(reply) },
                enabled = enabled,
                modifier = Modifier.heightIn(min = 48.dp).testTag("quickReply.${reply.wire}"),
            ) { Text(reply.label, maxLines = 1) }
        }
    }
}

/**
 * The large full-width buttons (CALL, Start call, SEND, STOP) the user must be able to hit
 * with the phone propped an arm away.
 */
@Composable
fun BigActionButton(
    text: String,
    tint: Color,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    foreground: Color = Color.White,
) {
    Button(
        onClick = onClick,
        enabled = enabled,
        shape = RoundedCornerShape(16.dp),
        colors = ButtonDefaults.buttonColors(containerColor = tint, contentColor = foreground),
        modifier = modifier.fillMaxWidth().heightIn(min = 64.dp),
    ) {
        Text(text, style = MaterialTheme.typography.headlineSmall.copy(fontWeight = FontWeight.Bold), textAlign = TextAlign.Center)
    }
}
