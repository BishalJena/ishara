package ai.ishara.demo.ui.home

import ai.ishara.demo.models.UserSettings
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp

/**
 * What Ishara says about the user on every call, kept on this phone. [forCall]: opened because
 * a call needs the name; its Call button continues the call (Cancel doesn't). Placeholder
 * layout; the next phase ports iOS `SettingsSheet` here. [onClose] gets whether to continue the call.
 */
@Composable
fun SettingsSheet(settings: UserSettings, forCall: Boolean, onClose: (continueCall: Boolean) -> Unit) {
    val hasName = settings.name.isNotBlank()
    AlertDialog(
        onDismissRequest = { onClose(false) },
        title = { Text(if (forCall) "Before the call" else "Settings") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                if (forCall) {
                    Text(
                        "Ishara introduces you by name on the call. Add it once; it stays on this phone.",
                        modifier = Modifier.testTag("settings.reason"),
                    )
                }
                OutlinedTextField(
                    value = settings.name,
                    onValueChange = settings::updateName,
                    label = { Text("Your name") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth().testTag("settings.name"),
                )
                OutlinedTextField(
                    value = settings.callback,
                    onValueChange = settings::updateCallback,
                    label = { Text("Callback number (optional)") },
                    prefix = { Text("+91 ") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
                    modifier = Modifier.fillMaxWidth().testTag("settings.callback"),
                )
                Text(
                    "Ishara gives the callback number only if they ask how to reach you. Every call opens by " +
                        "saying Ishara is calling for a Deaf caller, from Ishara's number, not yours.",
                )
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    settings.updateName(settings.name.trim())
                    onClose(forCall)
                },
                enabled = !forCall || hasName,
                modifier = Modifier.testTag("settings.done"),
            ) { Text(if (forCall) "Call" else "Done") }
        },
        dismissButton = if (forCall) ({ TextButton(onClick = { onClose(false) }) { Text("Cancel") } }) else null,
    )
}
