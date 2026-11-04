package ai.ishara.demo.ui.steer

import ai.ishara.demo.ui.notes.NotesModel
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

/**
 * The steer call's gist: outcome, how often the user stepped in, follow-ups and the transcript.
 * [model] is already polling. Placeholder layout; the next phase ports iOS `SteerGistView`
 * here, keeping these parameters.
 */
@Composable
fun SteerGistScreen(model: NotesModel, onDone: () -> Unit, onCallAgain: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Call with ${model.contactName}", style = MaterialTheme.typography.headlineSmall)
        model.failure?.let { Text(it) }
        model.notes?.let { notes ->
            Text(NotesModel.describe(notes.outcome, notes.ready), style = MaterialTheme.typography.titleLarge, modifier = Modifier.testTag("notes.outcome"))
            Text("You stepped in ${notes.steppedIn} times")
            notes.summary.forEach { Text("• $it") }
            if (notes.followUps.isNotEmpty()) {
                Column(modifier = Modifier.testTag("notes.followUps")) { notes.followUps.forEach { Text("↻ $it") } }
            }
            notes.bolnaSummary?.let { Text(it, modifier = Modifier.testTag("notes.bolnaSummary")) }
            notes.transcript.forEach { Text("${it.speaker.name.lowercase()}: ${it.text}") }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = onCallAgain, modifier = Modifier.testTag("notes.callAgain")) { Text("Call again") }
            Button(onClick = onDone, modifier = Modifier.testTag("notes.done")) { Text("Done") }
        }
    }
}
