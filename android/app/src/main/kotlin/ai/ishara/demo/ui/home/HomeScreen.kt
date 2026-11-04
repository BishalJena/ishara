package ai.ishara.demo.ui.home

import ai.ishara.demo.core.call.CallPurpose
import ai.ishara.demo.models.CallHistory
import ai.ishara.demo.models.CallSetup
import ai.ishara.demo.models.CallVoice
import ai.ishara.demo.models.Contact
import ai.ishara.demo.models.PreferredTime
import ai.ishara.demo.models.title
import ai.ishara.demo.ui.components.BottomBar
import ai.ishara.demo.ui.components.CallingNumberNote
import ai.ishara.demo.ui.components.FormDivider
import ai.ishara.demo.ui.components.FormRow
import ai.ishara.demo.ui.components.FormSection
import ai.ishara.demo.ui.components.LargeTitle
import ai.ishara.demo.ui.components.PrimaryButton
import ai.ishara.demo.ui.components.TonalButton
import ai.ishara.demo.ui.components.WarningLabel
import ai.ishara.demo.ui.components.isLargerThanExtraLargeText
import ai.ishara.demo.ui.theme.IsharaType
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material.icons.filled.Call
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Person
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp

/**
 * The classic Home (`IsharaFlow classic`, iOS `HomeView`): who to call, why, the saved details
 * and voice, then Call (sign every reply) or Call for me (D9). Both need a name and a call that
 * can be placed.
 */
@Composable
fun HomeScreen(
    setup: CallSetup,
    modeDescription: String,
    /** Why a call can't be placed right now (for example no backend configured). */
    setupProblem: String?,
    history: CallHistory,
    onCall: (CallSetup) -> Unit,
    onCallForMe: (CallSetup) -> Unit,
    onOpenRecent: (recordId: String) -> Unit,
) {
    var contactId by rememberSaveable { mutableStateOf(setup.contact.id) }
    var purpose by remember { mutableStateOf(setup.purpose) }
    var name by rememberSaveable { mutableStateOf(setup.details.name) }
    var preferredTime by rememberSaveable { mutableStateOf(setup.details.preferredTime) }
    var voice by remember { mutableStateOf(setup.voice) }
    val contact = Contact.demoContacts.firstOrNull { it.id == contactId } ?: setup.contact
    val chosen = setup.copy(
        contact = contact,
        purpose = purpose,
        details = setup.details.copy(name = name, preferredTime = preferredTime),
        voice = voice,
    )
    val canCall = name.isNotBlank() && setupProblem == null

    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.surfaceContainerLow)) {
        Column(
            modifier = Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(top = 24.dp, bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(24.dp),
        ) {
            LargeTitle("Ishara")
            FormSection(header = "Who do you want to call?") {
                Contact.demoContacts.forEach { option ->
                    val isChosen = option.id == contact.id
                    FormRow(
                        Modifier
                            .clickable(role = Role.RadioButton) { contactId = option.id }
                            .semantics { selected = isChosen }
                            .testTag("home.contact.${option.id}"),
                    ) {
                        Text(option.name, style = IsharaType.body, modifier = Modifier.weight(1f))
                        if (isChosen) Icon(Icons.Filled.Check, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                    }
                    FormDivider()
                }
                FormRow(Modifier.semantics(mergeDescendants = true) { contentDescription = "New contact, not available in the demo" }) {
                    Icon(Icons.Filled.Add, contentDescription = null, tint = MaterialTheme.colorScheme.onSurfaceVariant)
                    Spacer(Modifier.width(16.dp))
                    Text("New contact (coming later)", style = IsharaType.body, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            FormSection(header = "Purpose") {
                PickerRow("Purpose", purpose, CallPurpose.entries, { it.title }, { purpose = it }, "home.purpose")
            }
            FormSection(header = "My details", footer = "Used for quick replies and the drafted sentences.") {
                FormRow {
                    BasicTextField(
                        value = name,
                        onValueChange = { name = it },
                        textStyle = IsharaType.body.copy(color = MaterialTheme.colorScheme.onSurface),
                        cursorBrush = SolidColor(MaterialTheme.colorScheme.primary),
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Words, imeAction = ImeAction.Done),
                        modifier = Modifier.fillMaxWidth().testTag("home.name").semantics { contentDescription = "Your name" },
                        decorationBox = { field ->
                            Box {
                                if (name.isEmpty()) Text("Your name", style = IsharaType.body, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                field()
                            }
                        },
                    )
                }
                FormDivider()
                PickerRow("Preferred time", preferredTime, PreferredTime.entries, { it.title }, { preferredTime = it }, "home.preferredTime")
            }
            FormSection {
                PickerRow("Voice", voice, CallVoice.entries, { it.title }, { voice = it }, "home.voice")
            }
            // The section is laid out by its owner; it gets the Form's side margins here.
            Box(Modifier.padding(horizontal = 16.dp)) { RecentCallsSection(history, onOpenRecent) }
        }
        BottomBar {
            setupProblem?.let { WarningLabel(it, Modifier.fillMaxWidth().testTag("setup.problem"), style = IsharaType.footnote) }
            if (modeDescription.isNotEmpty()) {
                Text(modeDescription, style = IsharaType.footnote, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            CallingNumberNote()
            CallButtons(
                call = {
                    PrimaryButton(
                        "Call",
                        { onCall(chosen) },
                        it.testTag("home.call").semantics { contentDescription = "Call ${contact.name}" },
                        enabled = canCall,
                        icon = Icons.Filled.Call,
                    )
                },
                callForMe = {
                    TonalButton(
                        "Call for me",
                        { onCallForMe(chosen) },
                        it.testTag("home.callForMe").semantics { contentDescription = "Let the agent call ${contact.name} for you" },
                        enabled = canCall,
                        icon = Icons.Filled.Person,
                    )
                },
            )
        }
    }
}

/**
 * Call for me and Call side by side, Call (the primary) on the right; stacked full width once
 * the text is too large for both labels on one line.
 */
@Composable
private fun CallButtons(call: @Composable (Modifier) -> Unit, callForMe: @Composable (Modifier) -> Unit) {
    if (isLargerThanExtraLargeText()) {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            call(Modifier.fillMaxWidth())
            callForMe(Modifier.fillMaxWidth())
        }
    } else {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            callForMe(Modifier.weight(1f))
            call(Modifier.weight(1f))
        }
    }
}

/** iOS `Picker` in a Form row: the label, the chosen value, and a menu of the choices. */
@Composable
private fun <T> PickerRow(label: String, value: T, choices: List<T>, title: (T) -> String, onPick: (T) -> Unit, tag: String) {
    var expanded by remember { mutableStateOf(false) }
    Box {
        FormRow(Modifier.clickable(role = Role.DropdownList) { expanded = true }.testTag(tag)) {
            Text(label, style = IsharaType.body, modifier = Modifier.weight(1f))
            Text(title(value), style = IsharaType.body, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Icon(
                Icons.Filled.ArrowDropDown,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.size(24.dp),
            )
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            choices.forEach { choice ->
                DropdownMenuItem(
                    text = { Text(title(choice), style = IsharaType.body) },
                    trailingIcon = if (choice == value) ({ Icon(Icons.Filled.Check, contentDescription = null) }) else null,
                    onClick = {
                        expanded = false
                        onPick(choice)
                    },
                )
            }
        }
    }
}
