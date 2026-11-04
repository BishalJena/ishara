package ai.ishara.demo.ui.components

import ai.ishara.demo.ui.theme.IsharaColors
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Someone's initials, or "" (a person glyph) for a bare number or no name. */
fun initials(name: String): String {
    if (name.firstOrNull()?.isLetter() != true) return ""
    return name.split(" ").filter { it.isNotEmpty() }.take(2).map { it.first() }.joinToString("").uppercase()
}

/** A round avatar with someone's initials, or a person glyph when there's no name to take them from. */
@Composable
fun InitialsAvatar(name: String, modifier: Modifier = Modifier, color: Color = IsharaColors.Blue, size: Dp = 44.dp) {
    val letters = initials(name)
    Box(
        modifier = modifier.size(size).background(color, CircleShape).clearAndSetSemantics {},
        contentAlignment = Alignment.Center,
    ) {
        Text(
            letters.ifEmpty { "👤" },
            color = Color.White,
            fontWeight = FontWeight.Bold,
            fontSize = (size.value * 0.38f).sp,
        )
    }
}
