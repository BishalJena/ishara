package ai.ishara.demo.ui.home

import ai.ishara.demo.models.CallHistory
import ai.ishara.demo.models.CallSetup
import ai.ishara.demo.models.Contact
import ai.ishara.demo.ui.components.BigActionButton
import ai.ishara.demo.ui.components.CallingNumberNote
import ai.ishara.demo.ui.theme.IsharaColors
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

/**
 * The classic Home (`IsharaFlow classic`): who to call, then CALL (sign every reply) or CALL
 * FOR ME (D9). Placeholder layout; the next phase ports iOS `HomeView` here, keeping these
 * parameters.
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
    var contact by remember { mutableStateOf(setup.contact) }
    val chosen = setup.copy(contact = contact)
    val canCall = setupProblem == null
    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("Ishara", style = MaterialTheme.typography.headlineLarge)
        Text("Who to call", style = MaterialTheme.typography.titleMedium)
        Contact.demoContacts.forEach { option ->
            Row(
                modifier = Modifier.fillMaxWidth().clickable { contact = option },
                verticalAlignment = Alignment.CenterVertically,
            ) {
                RadioButton(selected = option == contact, onClick = { contact = option })
                Text(option.name)
            }
        }
        setupProblem?.let { Text(it, color = IsharaColors.Red, modifier = Modifier.testTag("setup.problem")) }
        BigActionButton("CALL", MaterialTheme.colorScheme.primary, { onCall(chosen) }, Modifier.testTag("home.call"), enabled = canCall)
        BigActionButton(
            "CALL FOR ME",
            IsharaColors.Purple,
            { onCallForMe(chosen) },
            Modifier.testTag("home.callForMe"),
            enabled = canCall,
        )
        CallingNumberNote()
        if (modeDescription.isNotEmpty()) {
            Text(modeDescription, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        RecentCallsSection(history, onOpenRecent)
    }
}
