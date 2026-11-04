package ai.ishara.demo.ui.steer

import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

/**
 * The iOS system colours the steer screens are drawn with (SwiftUI's `systemBackground`,
 * `secondarySystemBackground`, `.secondary`, `.purple`, …), in their light and dark values,
 * so the Android screens match the iOS ones in both appearances.
 */
@Immutable
data class SteerColors(
    val background: Color,
    val secondaryBackground: Color,
    val tertiaryBackground: Color,
    val groupedBackground: Color,
    val secondaryGroupedBackground: Color,
    val bar: Color,
    val primary: Color,
    val secondary: Color,
    val tertiary: Color,
    val separator: Color,
    val purple: Color,
    val blue: Color,
    val green: Color,
    val red: Color,
    val orange: Color,
    val yellow: Color,
    /** The facts strip's text, SwiftUI `Color(red: 0.6, green: 0.42, blue: 0)`. */
    val fact: Color,
) {
    companion object {
        val Light = SteerColors(
            background = Color.White,
            secondaryBackground = Color(0xFFF2F2F7),
            tertiaryBackground = Color.White,
            groupedBackground = Color(0xFFF2F2F7),
            secondaryGroupedBackground = Color.White,
            bar = Color(0xFFF9F9F9),
            primary = Color.Black,
            secondary = Color(0x993C3C43),
            tertiary = Color(0x4D3C3C43),
            separator = Color(0x4A3C3C43),
            purple = Color(0xFFAF52DE),
            blue = Color(0xFF007AFF),
            green = Color(0xFF34C759),
            red = Color(0xFFFF3B30),
            orange = Color(0xFFFF9500),
            yellow = Color(0xFFFFCC00),
            fact = Color(0xFF996B00),
        )

        val Dark = SteerColors(
            background = Color.Black,
            secondaryBackground = Color(0xFF1C1C1E),
            tertiaryBackground = Color(0xFF2C2C2E),
            groupedBackground = Color.Black,
            secondaryGroupedBackground = Color(0xFF1C1C1E),
            bar = Color(0xFF161618),
            primary = Color.White,
            secondary = Color(0x99EBEBF5),
            tertiary = Color(0x4DEBEBF5),
            separator = Color(0x99545458),
            purple = Color(0xFFBF5AF2),
            blue = Color(0xFF0A84FF),
            green = Color(0xFF30D158),
            red = Color(0xFFFF453A),
            orange = Color(0xFFFF9F0A),
            yellow = Color(0xFFFFD60A),
            fact = Color(0xFFE0B341),
        )
    }
}

/** SwiftUI's text styles at their default (Large) sizes, so the steer screens keep the iOS hierarchy. */
object SteerType {
    val title2 = TextStyle(fontSize = 22.sp, lineHeight = 28.sp)
    val title3 = TextStyle(fontSize = 20.sp, lineHeight = 25.sp)
    val headline = TextStyle(fontSize = 17.sp, lineHeight = 22.sp, fontWeight = FontWeight.SemiBold)
    val body = TextStyle(fontSize = 17.sp, lineHeight = 22.sp)
    val subheadline = TextStyle(fontSize = 15.sp, lineHeight = 20.sp)
    val footnote = TextStyle(fontSize = 13.sp, lineHeight = 18.sp)
    val caption = TextStyle(fontSize = 12.sp, lineHeight = 16.sp)
    val caption2 = TextStyle(fontSize = 11.sp, lineHeight = 13.sp)
}

/** Follows the app theme's appearance, so a forced dark theme (screenshots, tests) gets the dark values. */
@Composable
fun steerColors(): SteerColors = if (MaterialTheme.colorScheme.background.luminance() < 0.5f) SteerColors.Dark else SteerColors.Light
