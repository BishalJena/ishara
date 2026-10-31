package ai.ishara.demo.ui.components

import ai.ishara.demo.core.call.Chip
import ai.ishara.demo.core.call.Sign
import ai.ishara.demo.models.title
import ai.ishara.demo.ui.theme.IsharaColors
import ai.ishara.demo.ui.theme.IsharaType
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.onClick
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

/**
 * Recognised signs (green, ✕ removes) and unsure ones (red [?], never sent). Shows nothing
 * when empty: the draft card's "Sign your reply…" prompt already says what to do.
 */
@Composable
fun ChipRow(chips: List<Chip>, onRemove: (Chip) -> Unit, modifier: Modifier = Modifier) {
    if (chips.isEmpty()) return
    FlowRow(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        chips.forEach { chip -> ChipView(chip, onRemove = { onRemove(chip) }) }
    }
}

@Composable
fun ChipView(chip: Chip, onRemove: () -> Unit) {
    val sign = chip.sign
    val description = if (sign != null) "Recognised sign: ${sign.wire}" else "Unsure sign. It will not be sent. Try again."
    Row(
        modifier = Modifier
            .background(if (sign == null) IsharaColors.Red else IsharaColors.Green.copy(alpha = 0.75f), CircleShape)
            .clickable(role = Role.Button, onClickLabel = "Remove", onClick = onRemove)
            .semantics(mergeDescendants = true) { contentDescription = description }
            .testTag(chipTag(sign))
            .padding(horizontal = 12.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        val color = if (sign == null) Color.White else Color.Black
        Text(chip.title, color = color, style = IsharaType.body.copy(fontWeight = FontWeight.SemiBold))
        Icon(Icons.Filled.Close, contentDescription = null, tint = color, modifier = Modifier.size(14.dp))
    }
}

/** `chip.hello`, or `chip.unsure` for a [?] chip, like the iOS accessibility identifiers. */
fun chipTag(sign: Sign?): String = "chip.${sign?.wire ?: "unsure"}"
