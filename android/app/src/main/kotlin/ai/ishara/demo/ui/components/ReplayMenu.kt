package ai.ishara.demo.ui.components

import ai.ishara.demo.ui.theme.IsharaType
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.onClick
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

/**
 * Emulator only: it has no camera, so this plays a saved sign video (or a fixed result: a sign
 * name, `?`, `frame` or a `name?` candidate) through recognition. Hidden when the recognizer
 * offers nothing to replay. Sits over the camera card's bottom-right corner.
 */
@Composable
fun ReplayMenu(options: List<String>, onReplay: (String) -> Unit, modifier: Modifier = Modifier) {
    if (options.isEmpty()) return
    var expanded by remember { mutableStateOf(false) }
    Box(modifier) {
        Button(
            onClick = { expanded = true },
            shape = CircleShape,
            contentPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Color.White.copy(alpha = 0.85f), contentColor = Color.Black),
            modifier = Modifier
                .testTag("replayMenu")
                .semantics { onClick(label = "Play a saved sign through recognition, since the emulator has no camera") { expanded = true; true } },
        ) {
            Icon(Icons.Filled.PlayArrow, contentDescription = null, modifier = Modifier.size(18.dp))
            Spacer(Modifier.width(6.dp))
            Text("Replay a sign", style = IsharaType.subheadline.copy(fontWeight = FontWeight.SemiBold))
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            options.forEach { option ->
                DropdownMenuItem(
                    text = { Text(option, style = IsharaType.body) },
                    onClick = {
                        expanded = false
                        onReplay(option)
                    },
                    modifier = Modifier.testTag("replay.$option"),
                )
            }
        }
    }
}
