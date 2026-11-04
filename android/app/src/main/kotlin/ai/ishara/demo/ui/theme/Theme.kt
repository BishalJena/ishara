package ai.ishara.demo.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

/** The iOS AccentColor (Assets.xcassets): sRGB (0, 0.490, 0.180) light, (0.188, 0.820, 0.345) dark. */
val AccentLight = Color(0xFF007D2E)
val AccentDark = Color(0xFF30D158)

/** The status colours the iOS screens use (SwiftUI's system colours). */
object IsharaColors {
    val Green = Color(0xFF34C759)
    val Yellow = Color(0xFFFFCC00)
    val Red = Color(0xFFFF3B30)
    val Orange = Color(0xFFFF9500)
    val Purple = Color(0xFFAF52DE)
    val Blue = Color(0xFF007AFF)
    val Teal = Color(0xFF30B0C7)
    val Gray = Color(0xFF8E8E93)

    /** The camera card's dark backdrop (SwiftUI `Color(white: 0.2)`). */
    val CameraBackdrop = Color(0xFF333333)
}

// iOS system greys instead of Material's tinted baseline: background = systemBackground,
// surfaceVariant = secondarySystemBackground (`.background.secondary`), surfaceContainer = the
// bottom bars (`.bar`), surfaceContainerLow = systemGroupedBackground behind Form / List cards.
private val LightColors = lightColorScheme(
    primary = AccentLight,
    onPrimary = Color.White,
    secondary = AccentLight,
    onSecondary = Color.White,
    secondaryContainer = Color(0xFFE5E5EA),
    onSecondaryContainer = Color.Black,
    background = Color.White,
    onBackground = Color.Black,
    surface = Color.White,
    onSurface = Color.Black,
    surfaceVariant = Color(0xFFF2F2F7),
    onSurfaceVariant = Color(0xFF6C6C70),
    surfaceContainer = Color(0xFFF7F7F8),
    surfaceContainerLow = Color(0xFFF2F2F7),
    surfaceContainerHigh = Color(0xFFFFFFFF),
    surfaceContainerHighest = Color(0xFFE5E5EA),
    outline = Color(0xFFC6C6C8),
    outlineVariant = Color(0xFFE0E0E3),
)
private val DarkColors = darkColorScheme(
    primary = AccentDark,
    onPrimary = Color.Black,
    secondary = AccentDark,
    onSecondary = Color.Black,
    secondaryContainer = Color(0xFF3A3A3C),
    onSecondaryContainer = Color.White,
    background = Color.Black,
    onBackground = Color.White,
    surface = Color.Black,
    onSurface = Color.White,
    surfaceVariant = Color(0xFF1C1C1E),
    onSurfaceVariant = Color(0xFF98989F),
    surfaceContainer = Color(0xFF161618),
    surfaceContainerLow = Color.Black,
    surfaceContainerHigh = Color(0xFF1C1C1E),
    surfaceContainerHighest = Color(0xFF2C2C2E),
    outline = Color(0xFF545458),
    outlineVariant = Color(0xFF38383A),
)

@Composable
fun IsharaTheme(darkTheme: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (darkTheme) DarkColors else LightColors, content = content)
}
