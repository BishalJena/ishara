package ai.ishara.demo.ui.notes

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch

/**
 * D9 last step: the delegated call's notes (outcome, summary, open questions, transcript and
 * Bolna's own summary once it lands). [model] is already polling. Placeholder layout; the next
 * phase ports iOS `NotesView` here, keeping these parameters.
 */
@Composable
fun NotesScreen(model: NotesModel, onDone: () -> Unit) {
    val scope = rememberCoroutineScope()
    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Row {
            TextButton(onClick = onDone, modifier = Modifier.testTag("notes.done")) { Text("Done") }
            TextButton(
                onClick = { scope.launch { model.refresh() } },
                enabled = !model.isLoading,
                modifier = Modifier.testTag("notes.refresh"),
            ) { Text("Refresh") }
        }
        Text("Call with ${model.contactName}", style = MaterialTheme.typography.headlineSmall)
        model.failure?.let { Text(it) }
        model.notes?.let { notes ->
            Text(NotesModel.describe(notes.outcome, notes.ready), style = MaterialTheme.typography.titleLarge, modifier = Modifier.testTag("notes.outcome"))
            notes.summary.forEach { Text("• $it") }
            notes.openQuestions.forEach { Text("? $it") }
            notes.bolnaSummary?.let { Text(it, modifier = Modifier.testTag("notes.bolnaSummary")) }
            notes.transcript.forEach { Text("${it.speaker.name.lowercase()}: ${it.text}") }
        }
    }
}
