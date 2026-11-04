package ai.ishara.demo.ui.components

import ai.ishara.demo.ui.theme.IsharaColors
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.IconButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/*
 * The app's button tiers, in Material 3 proportions. One primary per screen; everything else is
 * tonal, text or icon. Every target is at least 48 dp (Material buttons add the touch margin
 * themselves), and the heights are minimums, so labels may grow with the font scale.
 *
 * | Tier        | Height | Label           | Use                                      |
 * |-------------|--------|-----------------|------------------------------------------|
 * | Primary     | 48 dp  | 16 sp semibold  | Call, Start call, Send, Approve and call |
 * | Tonal       | 48 dp  | 16 sp semibold  | Call for me, Back to Home, call notes    |
 * | Text        | 40 dp  | 15 sp semibold  | Clear, Back                              |
 * | Destructive | 56 dp  | 17 sp bold      | Stop (the biggest target while speaking) |
 * | Icon        | 40 dp  | –               | send arrow, toggles, delete              |
 */

object IsharaButtons {
    val Height = 48.dp
    val TextHeight = 40.dp
    val DestructiveHeight = 56.dp
    val IconSize = 20.dp
    val Label = TextStyle(fontSize = 16.sp, lineHeight = 20.sp, fontWeight = FontWeight.SemiBold)
    val TextLabel = TextStyle(fontSize = 15.sp, lineHeight = 20.sp, fontWeight = FontWeight.SemiBold)
    val DestructiveLabel = TextStyle(fontSize = 17.sp, lineHeight = 22.sp, fontWeight = FontWeight.Bold)
}

/** The screen's one main action, filled in the accent colour. [fillWidth] for a bottom bar's lone primary. */
@Composable
fun PrimaryButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    icon: ImageVector? = null,
    fillWidth: Boolean = false,
) {
    Button(
        onClick = onClick,
        enabled = enabled,
        shape = CircleShape,
        contentPadding = PaddingValues(horizontal = 24.dp, vertical = 10.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = MaterialTheme.colorScheme.primary,
            contentColor = MaterialTheme.colorScheme.onPrimary,
        ),
        modifier = modifier.widthIf(fillWidth).heightIn(min = IsharaButtons.Height),
    ) { ButtonContent(text, icon, IsharaButtons.Label, IsharaButtons.IconSize) }
}

/** A secondary action: [tint] over a light wash of itself. */
@Composable
fun TonalButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    icon: ImageVector? = null,
    tint: Color = MaterialTheme.colorScheme.primary,
    fillWidth: Boolean = false,
) {
    Button(
        onClick = onClick,
        enabled = enabled,
        shape = CircleShape,
        contentPadding = PaddingValues(horizontal = 20.dp, vertical = 10.dp),
        colors = ButtonDefaults.buttonColors(containerColor = tint.copy(alpha = 0.14f), contentColor = tint),
        modifier = modifier.widthIf(fillWidth).heightIn(min = IsharaButtons.Height),
    ) { ButtonContent(text, icon, IsharaButtons.Label, IsharaButtons.IconSize) }
}

/** A quiet action sized to its label (Clear, Back). */
@Composable
fun IsharaTextButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    color: Color = MaterialTheme.colorScheme.primary,
) {
    TextButton(
        onClick = onClick,
        enabled = enabled,
        contentPadding = PaddingValues(horizontal = 12.dp, vertical = 8.dp),
        colors = ButtonDefaults.textButtonColors(contentColor = color),
        modifier = modifier.heightIn(min = IsharaButtons.TextHeight),
    ) { Text(text, style = IsharaButtons.TextLabel, textAlign = TextAlign.Center) }
}

/** Stop: red, and the biggest target on the screen while a reply is spoken. */
@Composable
fun DestructiveButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    icon: ImageVector? = null,
) {
    Button(
        onClick = onClick,
        enabled = enabled,
        shape = CircleShape,
        contentPadding = PaddingValues(horizontal = 24.dp, vertical = 12.dp),
        colors = ButtonDefaults.buttonColors(containerColor = IsharaColors.Red, contentColor = Color.White),
        modifier = modifier.fillMaxWidth().heightIn(min = IsharaButtons.DestructiveHeight),
    ) { ButtonContent(text, icon, IsharaButtons.DestructiveLabel, IsharaButtons.IconSize) }
}

/** An icon-only action (40 dp, 48 dp target); [filled] puts it on an accent circle. */
@Composable
fun IsharaIconButton(
    icon: ImageVector,
    contentDescription: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    filled: Boolean = false,
    tint: Color = if (filled) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurfaceVariant,
    iconSize: Dp = IsharaButtons.IconSize,
) {
    if (filled) {
        FilledIconButton(
            onClick = onClick,
            enabled = enabled,
            colors = IconButtonDefaults.filledIconButtonColors(containerColor = MaterialTheme.colorScheme.primary, contentColor = tint),
            modifier = modifier,
        ) { Icon(icon, contentDescription, Modifier.size(iconSize)) }
    } else {
        IconButton(onClick = onClick, enabled = enabled, modifier = modifier) {
            Icon(icon, contentDescription, Modifier.size(iconSize), tint = tint)
        }
    }
}

@Composable
private fun RowScope.ButtonContent(text: String, icon: ImageVector?, style: TextStyle, iconSize: Dp) {
    if (icon != null) {
        Icon(icon, contentDescription = null, modifier = Modifier.size(iconSize).clearAndSetSemantics {})
        Spacer(Modifier.width(8.dp))
    }
    Text(text, style = style, textAlign = TextAlign.Center)
}

private fun Modifier.widthIf(fill: Boolean): Modifier = if (fill) fillMaxWidth() else this
