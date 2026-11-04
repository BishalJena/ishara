package ai.ishara.demo.ui.components

import ai.ishara.demo.ui.theme.IsharaColors
import ai.ishara.demo.ui.theme.IsharaType
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

/*
 * Small building blocks for the iOS look: Dynamic Type classes from the font scale, the bottom
 * bar, large titles, grouped Form sections, bordered buttons and labelled messages.
 */

/**
 * Android's font scale against iOS Dynamic Type: the default 1.0 is iOS Large; the
 * accessibility sizes (AX1 is 28 pt body against 17 pt, × 1.65) start past 1.6, so only
 * Android's 1.8 and 2.0 count; 1.3 and up is larger than iOS XL (19 pt, × 1.12).
 */
object TextSizes {
    const val ACCESSIBILITY_SCALE = 1.6f
    const val EXTRA_LARGE_SCALE = 1.2f
}

/** iOS `dynamicTypeSize.isAccessibilitySize`. */
@Composable
fun isAccessibilityTextSize(): Boolean = LocalDensity.current.fontScale >= TextSizes.ACCESSIBILITY_SCALE

/** iOS `dynamicTypeSize > .xLarge`. */
@Composable
fun isLargerThanExtraLargeText(): Boolean = LocalDensity.current.fontScale > TextSizes.EXTRA_LARGE_SCALE

/** The bar pinned under a screen (iOS `.safeAreaInset(edge: .bottom)` with `.background(.bar)`). */
@Composable
fun BottomBar(modifier: Modifier = Modifier, spacing: Dp = 8.dp, content: @Composable ColumnScope.() -> Unit) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surfaceContainer)
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(spacing),
        content = content,
    )
}

/** The top row of a pushed screen: a leading action, an optional inline title, a trailing action. */
@Composable
fun TopBar(
    modifier: Modifier = Modifier,
    title: String? = null,
    leading: @Composable RowScope.() -> Unit = {},
    trailing: @Composable RowScope.() -> Unit = {},
) {
    Box(modifier.fillMaxWidth().heightIn(min = 48.dp).padding(horizontal = 4.dp)) {
        Row(Modifier.align(Alignment.CenterStart), verticalAlignment = Alignment.CenterVertically, content = leading)
        if (title != null) {
            Text(title, style = IsharaType.headline, modifier = Modifier.align(Alignment.Center))
        }
        Row(Modifier.align(Alignment.CenterEnd), verticalAlignment = Alignment.CenterVertically, content = trailing)
    }
}

/** iOS `.navigationTitle` in its large form. */
@Composable
fun LargeTitle(text: String, modifier: Modifier = Modifier) {
    Text(
        text,
        style = IsharaType.largeTitle,
        modifier = modifier.padding(horizontal = 16.dp).semantics { heading() },
    )
}

/** iOS `.buttonStyle(.bordered)`: the tint over a light wash of itself. */
@Composable
fun BorderedButton(
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    tint: Color = MaterialTheme.colorScheme.primary,
    enabled: Boolean = true,
    shape: Shape = RoundedCornerShape(percent = 50),
    contentPadding: PaddingValues = PaddingValues(horizontal = 14.dp, vertical = 8.dp),
    content: @Composable RowScope.() -> Unit,
) {
    Button(
        onClick = onClick,
        enabled = enabled,
        shape = shape,
        contentPadding = contentPadding,
        colors = ButtonDefaults.buttonColors(
            containerColor = tint.copy(alpha = 0.15f),
            contentColor = tint,
            disabledContainerColor = IsharaColors.Gray.copy(alpha = 0.12f),
            disabledContentColor = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f),
        ),
        modifier = modifier,
        content = content,
    )
}

/** A grouped Form / List section: a header, white rounded rows with separators, a footer. */
@Composable
fun FormSection(
    modifier: Modifier = Modifier,
    header: String? = null,
    footer: String? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    Column(modifier.fillMaxWidth().padding(horizontal = 16.dp)) {
        if (header != null) {
            Text(
                header,
                style = IsharaType.footnote,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(start = 16.dp, end = 16.dp, bottom = 6.dp).semantics { heading() },
            )
        }
        Column(
            Modifier
                .fillMaxWidth()
                .background(MaterialTheme.colorScheme.surfaceContainerHigh, RoundedCornerShape(12.dp)),
            content = content,
        )
        if (footer != null) {
            Text(
                footer,
                style = IsharaType.footnote,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(start = 16.dp, end = 16.dp, top = 6.dp),
            )
        }
    }
}

/** The separator between two rows of a [FormSection]. */
@Composable
fun FormDivider() {
    HorizontalDivider(Modifier.padding(start = 16.dp), color = MaterialTheme.colorScheme.outlineVariant)
}

/** A row of a [FormSection]. */
@Composable
fun FormRow(modifier: Modifier = Modifier, content: @Composable RowScope.() -> Unit) {
    Row(
        modifier = modifier.fillMaxWidth().heightIn(min = 48.dp).padding(horizontal = 16.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        content = content,
    )
}

/** iOS `Label(text, systemImage:)`: an icon before the text, both in [color]. */
@Composable
fun IconLabel(
    text: String,
    icon: ImageVector,
    modifier: Modifier = Modifier,
    color: Color = MaterialTheme.colorScheme.onSurface,
    style: TextStyle = IsharaType.body,
) {
    // Read (and found by tests) as one element.
    Row(modifier.semantics(mergeDescendants = true) {}, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Icon(icon, contentDescription = null, tint = color, modifier = Modifier.padding(top = 2.dp).size(with(LocalDensity.current) { style.fontSize.toDp() }))
        Text(text, style = style, color = color)
    }
}

/** A red warning: why something can't happen. */
@Composable
fun WarningLabel(text: String, modifier: Modifier = Modifier, style: TextStyle = IsharaType.body) {
    IconLabel(text, Icons.Filled.Warning, modifier, color = IsharaColors.Red, style = style)
}

/** A quiet note that doesn't stop anything. */
@Composable
fun InfoLabel(text: String, modifier: Modifier = Modifier, style: TextStyle = IsharaType.body) {
    IconLabel(text, Icons.Filled.Info, modifier, color = MaterialTheme.colorScheme.onSurfaceVariant, style = style)
}

/**
 * Shows [content] at its natural height when it fits in [maxHeight], and only otherwise lets
 * it scroll inside, so the buttons below it stay on screen (iOS `PinnedSentence`).
 */
@Composable
fun PinnedSentence(maxHeight: Dp, modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    Box(modifier.fillMaxWidth().heightIn(max = maxHeight).verticalScroll(rememberScrollState())) { content() }
}
