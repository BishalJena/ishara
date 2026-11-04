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

private val LightColors = lightColorScheme(primary = AccentLight, onPrimary = Color.White)
private val DarkColors = darkColorScheme(primary = AccentDark, onPrimary = Color.Black)

@Composable
fun IsharaTheme(darkTheme: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (darkTheme) DarkColors else LightColors, content = content)
}
