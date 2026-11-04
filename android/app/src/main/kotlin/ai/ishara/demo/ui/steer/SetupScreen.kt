package ai.ishara.demo.ui.steer

import ai.ishara.demo.models.CallHistory
import ai.ishara.demo.models.Contact
import ai.ishara.demo.models.SetupDraft
import ai.ishara.demo.models.UserSettings
import ai.ishara.demo.ui.components.BigActionButton
import ai.ishara.demo.ui.home.RecentCallsSection
import ai.ishara.demo.ui.theme.IsharaColors
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp

/**
 * Home for steer calls (the default flow): who to call (a typed number or someone called
 * before), what the call is about, and any document Ishara may quote from. [onCall] places it
 * (the navigator asks for the caller's name first if none is saved). Placeholder layout; the
 * next phase ports iOS `SetupView` here (contact picker, attachments), keeping these parameters.
 */
@Composable
fun SetupScreen(
    draft: SetupDraft,
    settings: UserSettings,
    history: CallHistory,
    modeDescription: String,
    /** Why a call can't be placed right now (no backend configured, or the brief failed). */
    setupProblem: String?,
    onCall: () -> Unit,
    onOpenSettings: () -> Unit,
    onOpenRecent: (recordId: String) -> Unit,
) {
    val problem = draft.problem(setupProblem)
    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Row {
            Text("Ishara", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
            TextButton(onClick = onOpenSettings, modifier = Modifier.testTag("setup.settings")) {
                Text(settings.name.ifBlank { "Settings" })
            }
        }
        Text("Who are we\ncalling today?", style = MaterialTheme.typography.headlineLarge)
        SetupDraft.recentPeople(history.records).takeIf { it.isNotEmpty() }?.let { people ->
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.testTag("setup.recentPeople")) {
                people.forEach { person ->
                    OutlinedButton(onClick = {
                        draft.pickedName = person.name
                        draft.number = Contact.indianDigits(person.phoneNumber.orEmpty())
                    }) { Text(person.name) }
                }
            }
        }
        OutlinedTextField(
            value = draft.number,
            onValueChange = { draft.number = it.filter(Char::isDigit).take(10) },
            label = { Text("Number") },
            prefix = { Text("+91 ") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
            modifier = Modifier.fillMaxWidth().testTag("setup.number"),
        )
        OutlinedTextField(
            value = draft.request,
            onValueChange = { draft.request = it },
            label = { Text("What's the call about?") },
            minLines = 3,
            modifier = Modifier.fillMaxWidth().testTag("setup.request"),
        )
        problem?.let { Text(it, color = IsharaColors.Red, modifier = Modifier.testTag("setup.problem")) }
        BigActionButton("Call", MaterialTheme.colorScheme.primary, onCall, Modifier.testTag("setup.call"), enabled = problem == null)
        Text(
            "Ishara leads the call from what you wrote and never adds anything else. It calls from Ishara's number, not yours. $modeDescription",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        RecentCallsSection(history, onOpenRecent)
    }
}
