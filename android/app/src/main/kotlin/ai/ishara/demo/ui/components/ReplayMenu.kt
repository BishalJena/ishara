package ai.ishara.demo.ui.components

import ai.ishara.demo.ui.theme.IsharaType
import androidx.compose.foundation.layout.Box
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
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

/**
 * Emulator only: it has no camera, so this plays a saved sign video (or a fixed result: a sign
 * name, `?`, `frame` or a `name?` candidate) through recognition. Hidden when the recognizer
 * offers nothing to replay. [tint] White over Get ready's dark camera card.
 */
@Composable
fun ReplayMenu(options: List<String>, onReplay: (String) -> Unit, modifier: Modifier = Modifier, tint: Color = MaterialTheme.colorScheme.primary) {
    if (options.isEmpty()) return
    var expanded by remember { mutableStateOf(false) }
    Box(modifier) {
        TonalButton(
            "Replay a sign",
            { expanded = true },
            Modifier
                .testTag("replayMenu")
                .semantics { onClick(label = "Play a saved sign through recognition, since the emulator has no camera") { expanded = true; true } },
            icon = Icons.Filled.PlayArrow,
            tint = tint,
        )
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
