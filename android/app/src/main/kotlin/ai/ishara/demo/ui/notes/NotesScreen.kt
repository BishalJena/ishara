package ai.ishara.demo.ui.notes

import ai.ishara.demo.core.call.CallNotes
import ai.ishara.demo.core.call.CaptionSpeaker
import ai.ishara.demo.ui.components.FormDivider
import ai.ishara.demo.ui.components.FormSection
import ai.ishara.demo.ui.components.IconLabel
import ai.ishara.demo.ui.components.LargeTitle
import ai.ishara.demo.ui.components.TopBar
import ai.ishara.demo.ui.components.WarningLabel
import ai.ishara.demo.ui.theme.IsharaColors
import ai.ishara.demo.ui.theme.IsharaType
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch

/**
 * The notes after a delegated call (D9, iOS `NotesView`): outcome, what happened, what is still
 * open, the brief and the full transcript. Summaries can be wrong; the transcript is what was
 * actually said. [model] loads them on its own (`NotesModel.start()`); this screen only shows them.
 */
@Composable
fun NotesScreen(model: NotesModel, onDone: () -> Unit) {
    val scope = rememberCoroutineScope()
    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.surfaceContainerLow)) {
        TopBar(
            leading = {
                IconButton(
                    onClick = { scope.launch { model.refresh() } },
                    enabled = !model.isLoading,
                    modifier = Modifier.testTag("notes.refresh").semantics { contentDescription = "Refresh" },
                ) { Icon(Icons.Filled.Refresh, contentDescription = null) }
            },
            trailing = {
                TextButton(onClick = onDone, modifier = Modifier.testTag("notes.done")) {
                    Text("Done", style = IsharaType.body.copy(fontWeight = FontWeight.SemiBold))
                }
            },
        )
        Column(
            modifier = Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(24.dp),
        ) {
            LargeTitle("Call notes")
            val notes = model.notes
            val failure = model.failure
            if (notes != null) {
                NotesSections(notes, model.contactName)
            } else if (failure == null) {
                Row(
                    Modifier.fillMaxWidth().padding(16.dp),
                    horizontalArrangement = Arrangement.spacedBy(12.dp, Alignment.CenterHorizontally),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                    Text("Loading the notes…", style = IsharaType.body, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            if (failure != null) {
                FormSection { NotesRow { WarningLabel(failure, Modifier.testTag("notes.failure")) } }
            }
        }
    }
}

/** The notes themselves, shared by the notes screen after a call and a saved call in Recent calls. */
@Composable
fun NotesSections(notes: CallNotes, contactName: String) {
    Column(verticalArrangement = Arrangement.spacedBy(24.dp)) {
        FormSection(header = "Call with $contactName") {
            NotesRow {
                OutcomeLabel(
                    NotesModel.describe(notes.outcome, notes.ready),
                    booked = notes.outcome == "booked",
                )
            }
        }
        if (notes.summary.isNotEmpty()) {
            FormSection(header = "What happened") { Rows(notes.summary) { Text(it, style = IsharaType.body) } }
        }
        if (notes.openQuestions.isNotEmpty()) {
            FormSection(header = "Still open") {
                Rows(notes.openQuestions) { IconLabel(it, Icons.Filled.Info, color = IsharaColors.Orange) }
            }
        }
        notes.brief?.let { brief ->
            FormSection(header = "The brief you approved") { NotesRow { Text(brief, style = IsharaType.body) } }
        }
        FormSection(header = "Transcript") {
            if (notes.transcript.isEmpty()) {
                NotesRow { Text("Nothing was heard on the call.", style = IsharaType.body, color = MaterialTheme.colorScheme.onSurfaceVariant) }
            }
            Rows(notes.transcript) { entry ->
                val isAgent = entry.speaker == CaptionSpeaker.AGENT
                TranscriptRow(if (isAgent) "Agent (for you)" else "They said", entry.text, isAgent)
            }
        }
        notes.bolnaSummary?.let { summary ->
            FormSection(
                header = "Automatic summary",
                footer = "Written by the call service's AI. It can be wrong; the transcript is what was said.",
            ) {
                NotesRow { Text(summary, style = IsharaType.body, modifier = Modifier.testTag("notes.bolnaSummary")) }
            }
        }
    }
}

@Composable
private fun <T> Rows(items: List<T>, row: @Composable (T) -> Unit) {
    items.forEachIndexed { index, item ->
        if (index > 0) FormDivider()
        NotesRow { row(item) }
    }
}

@Composable
private fun NotesRow(content: @Composable () -> Unit) {
    Column(Modifier.fillMaxWidth().heightIn(min = 44.dp).padding(horizontal = 16.dp, vertical = 11.dp)) { content() }
}

/** The call's outcome, read as one element. */
@Composable
fun OutcomeLabel(text: String, booked: Boolean) {
    Row(
        modifier = Modifier.semantics(mergeDescendants = true) {}.testTag("notes.outcome"),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            if (booked) Icons.Filled.CheckCircle else Icons.Filled.Info,
            contentDescription = null,
            tint = if (booked) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.size(24.dp),
        )
        Text(text, style = IsharaType.headline)
    }
}

/** One line of a call's transcript: who spoke, then what they said. */
@Composable
fun TranscriptRow(speaker: String, text: String, isAgent: Boolean) {
    Column(Modifier.semantics(mergeDescendants = true) {}, verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(
            speaker,
            style = IsharaType.caption.copy(fontWeight = FontWeight.SemiBold),
            color = if (isAgent) IsharaColors.Blue else MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(text, style = IsharaType.body)
    }
}
