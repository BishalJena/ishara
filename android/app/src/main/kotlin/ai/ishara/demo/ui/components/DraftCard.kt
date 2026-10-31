package ai.ishara.demo.ui.components

import ai.ishara.demo.core.call.QuickReply
import ai.ishara.demo.models.DraftBadge
import ai.ishara.demo.models.DraftDisplay
import ai.ishara.demo.models.label
import ai.ishara.demo.models.wire
import ai.ishara.demo.ui.theme.IsharaColors
import ai.ishara.demo.ui.theme.IsharaType
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
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
            // The text stays readable to tests (and TalkBack reads the one description).
            .semantics(mergeDescendants = true) { contentDescription = description }
            .testTag("call.draft")
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                "Draft",
                style = IsharaType.subheadline.copy(fontWeight = FontWeight.SemiBold),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.weight(1f))
            if (draft != null) SourceBadge(draft.badge)
        }
        when {
            draft != null -> Text("\u201C${draft.text}\u201D", style = IsharaType.title3)
            isComposing -> Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Text("Composing…", style = IsharaType.body, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            else -> Text("Sign your reply or pick a quick reply.", style = IsharaType.body, color = MaterialTheme.colorScheme.onSurfaceVariant)
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
        style = IsharaType.caption.copy(fontWeight = FontWeight.Bold),
        modifier = Modifier
            .background(color, CircleShape)
            .padding(horizontal = 8.dp, vertical = 3.dp)
            .testTag("call.draftBadge"),
    )
}

/**
 * Yes / No / Wait / Repeat. Each puts a full sentence in the draft; SEND is still needed.
 * The four share the width evenly when their one-line labels fit; at large text sizes the row
 * scrolls sideways instead of wrapping into a tall grid that hid the draft (iOS `ViewThatFits`).
 */
@Composable
fun QuickReplyBar(onChoose: (QuickReply) -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true) {
    val spacing = 8.dp
    val measurer = rememberTextMeasurer()
    BoxWithConstraints(modifier.fillMaxWidth()) {
        val density = LocalDensity.current
        val needed = with(density) {
            QuickReply.entries.sumOf { reply ->
                measurer.measure(reply.label, IsharaType.body, softWrap = false).size.width + QUICK_REPLY_PADDING.roundToPx() * 2
            } + spacing.roundToPx() * (QuickReply.entries.size - 1)
        }
        val fits = needed <= constraints.maxWidth
        if (fits) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(spacing)) {
                QuickReplyButtons(onChoose, enabled, Modifier.weight(1f))
            }
        } else {
            Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(spacing)) {
                QuickReplyButtons(onChoose, enabled, Modifier)
            }
        }
    }
}

private val QUICK_REPLY_PADDING = 16.dp

@Composable
private fun QuickReplyButtons(onChoose: (QuickReply) -> Unit, enabled: Boolean, modifier: Modifier) {
    QuickReply.entries.forEach { reply ->
        BorderedButton(
            onClick = { onChoose(reply) },
            enabled = enabled,
            contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = QUICK_REPLY_PADDING, vertical = 12.dp),
            modifier = modifier.heightIn(min = 50.dp).testTag("quickReply.${reply.wire}"),
        ) { Text(reply.label, style = IsharaType.body, maxLines = 1, softWrap = false) }
    }
}

/**
 * The large full-width buttons (CALL, Start call, SEND, STOP) the user must be able to hit
 * with the phone propped an arm away. Disabled, they turn grey like iOS `BigActionButtonStyle`.
 */
@Composable
fun BigActionButton(
    text: String,
    tint: Color,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    foreground: Color = Color.White,
    icon: ImageVector? = null,
    fillWidth: Boolean = true,
) {
    Button(
        onClick = onClick,
        enabled = enabled,
        shape = RoundedCornerShape(16.dp),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 12.dp, vertical = 8.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = tint,
            contentColor = foreground,
            disabledContainerColor = IsharaColors.Gray.copy(alpha = 0.25f),
            disabledContentColor = MaterialTheme.colorScheme.onSurfaceVariant,
        ),
        modifier = modifier.then(if (fillWidth) Modifier.fillMaxWidth() else Modifier).heightIn(min = 64.dp),
    ) {
        if (icon != null) {
            Icon(icon, contentDescription = null, modifier = Modifier.size(24.dp).clearAndSetSemantics {})
            Spacer(Modifier.width(10.dp))
        }
        Text(text, style = IsharaType.title2.copy(fontWeight = FontWeight.Bold), textAlign = TextAlign.Center)
    }
}
