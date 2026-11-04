package ai.ishara.demo.ui.home

import ai.ishara.demo.models.UserSettings
import ai.ishara.demo.ui.steer.PlainField
import ai.ishara.demo.ui.steer.SteerType
import ai.ishara.demo.ui.steer.steerColors
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.RecordVoiceOver
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp

/**
 * What Ishara says about the user on every call, kept on this phone (port of iOS
 * `SettingsSheet`). [forCall]: opened because a call needs the name; it says why, focuses the
 * field, and its Call button continues the call (Cancel and swiping it away don't).
 * [onClose] gets whether to continue the call.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsSheet(settings: UserSettings, forCall: Boolean, onClose: (continueCall: Boolean) -> Unit) {
    val colors = steerColors()
    val hasName = settings.name.isNotBlank()
    val nameFocus = remember { FocusRequester() }
    fun continueCall() {
        settings.updateName(settings.name.trim())
        onClose(true)
    }
    ModalBottomSheet(
        onDismissRequest = { onClose(false) },
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = colors.groupedBackground,
        modifier = Modifier.testTag("settings.sheet"),
    ) {
        Column(Modifier.fillMaxWidth().imePadding().padding(bottom = 24.dp)) {
            Box(Modifier.fillMaxWidth().padding(horizontal = 8.dp)) {
                if (forCall) {
                    TextButton(onClick = { onClose(false) }, modifier = Modifier.align(Alignment.CenterStart).testTag("settings.cancel")) {
                        Text("Cancel", style = SteerType.body, color = colors.blue)
                    }
                }
                Text(
                    if (forCall) "Before the call" else "Settings",
                    style = SteerType.headline,
                    color = colors.primary,
                    modifier = Modifier.align(Alignment.Center),
                )
                TextButton(
                    onClick = { if (forCall) continueCall() else onClose(false) },
                    enabled = !forCall || hasName,
                    modifier = Modifier.align(Alignment.CenterEnd).testTag("settings.done"),
                ) {
                    Text(
                        if (forCall) "Call" else "Done",
                        style = SteerType.headline,
                        color = if (!forCall || hasName) colors.blue else colors.tertiary,
                    )
                }
            }
            Column(Modifier.padding(horizontal = 16.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(24.dp)) {
                if (forCall) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(10.dp))
                            .background(colors.secondaryGroupedBackground)
                            .padding(horizontal = 16.dp, vertical = 12.dp)
                            .testTag("settings.reason"),
                    ) {
                        Icon(Icons.Filled.RecordVoiceOver, contentDescription = null, tint = colors.blue, modifier = Modifier.size(22.dp))
                        Text(
                            "Ishara introduces you by name on the call. Add it once; it stays on this phone.",
                            style = SteerType.subheadline,
                            color = colors.primary,
                        )
                    }
                }
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("ABOUT YOU", style = SteerType.footnote, color = colors.secondary, modifier = Modifier.padding(horizontal = 16.dp))
                    Column(
                        Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(10.dp))
                            .background(colors.secondaryGroupedBackground),
                    ) {
                        PlainField(
                            value = settings.name,
                            onValueChange = settings::updateName,
                            placeholder = "Your name",
                            style = SteerType.body,
                            singleLine = true,
                            keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Words, imeAction = ImeAction.Done),
                            keyboardActions = KeyboardActions(onDone = { if (forCall && hasName) continueCall() }),
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = 16.dp, vertical = 12.dp)
                                .focusRequester(nameFocus)
                                .testTag("settings.name"),
                        )
                        HorizontalDivider(color = colors.separator, thickness = 0.5.dp, modifier = Modifier.padding(start = 16.dp))
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(6.dp),
                            modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp),
                        ) {
                            Text("+91", style = SteerType.body, color = colors.secondary)
                            PlainField(
                                value = settings.callback,
                                onValueChange = settings::updateCallback,
                                placeholder = "Callback number (optional)",
                                style = SteerType.body,
                                keyboardType = KeyboardType.Phone,
                                singleLine = true,
                                modifier = Modifier.weight(1f).testTag("settings.callback"),
                            )
                        }
                    }
                    Text(
                        "Ishara gives the callback number only if they ask how to reach you. Every call opens by saying " +
                            "Ishara is calling for a Deaf caller, from Ishara's number, not yours.",
                        style = SteerType.footnote,
                        fontWeight = FontWeight.Normal,
                        color = colors.secondary,
                        modifier = Modifier.padding(horizontal = 16.dp),
                    )
                }
            }
            LaunchedEffect(forCall) { if (forCall) nameFocus.requestFocus() }
        }
    }
}
