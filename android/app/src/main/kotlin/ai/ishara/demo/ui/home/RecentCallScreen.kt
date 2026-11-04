package ai.ishara.demo.ui.home

import ai.ishara.demo.core.call.CallMode
import ai.ishara.demo.models.CallHistory
import ai.ishara.demo.models.CallRecord
import ai.ishara.demo.ui.notes.NotesModel
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
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import java.text.DateFormat
import java.util.Date

/** Recent calls on Home: newest first, one row each. Placeholder layout (iOS `RecentCallsSection`). */
@Composable
fun RecentCallsSection(history: CallHistory, onOpen: (recordId: String) -> Unit) {
    if (history.records.isEmpty() && history.problem == null) return
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("Recent calls", style = MaterialTheme.typography.titleMedium)
        history.problem?.let { Text(it, modifier = Modifier.testTag("recentCalls.problem")) }
        history.records.forEach { record ->
            Row(modifier = Modifier.fillMaxWidth().clickable { onOpen(record.id) }.padding(vertical = 8.dp).testTag("recentCalls.row")) {
                Text("${record.contactName} · ${formatDate(record.date)}")
            }
        }
    }
}

/**
 * One saved call, read-only: its captions, or its notes for a Call for me call. Placeholder
 * layout; the next phase ports iOS `RecentCallView` here. [record] is null once deleted.
 */
@Composable
fun RecentCallScreen(record: CallRecord?, onBack: () -> Unit, onDelete: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        TextButton(onClick = onBack) { Text("Back") }
        if (record == null) {
            Text("This call is no longer saved.")
            return
        }
        Text(record.contactName, style = MaterialTheme.typography.headlineSmall)
        Text(formatDate(record.date), color = MaterialTheme.colorScheme.onSurfaceVariant)
        record.notes?.let { notes ->
            Text(NotesModel.describe(notes.outcome, notes.ready), style = MaterialTheme.typography.titleMedium)
            notes.bolnaSummary?.let { Text(it) }
        }
        record.captions.forEach { line ->
            Text("${speakerName(line.speaker, record)}: ${line.text}")
        }
        TextButton(onClick = onDelete) { Text("Delete this call") }
    }
}

private fun speakerName(speaker: CallRecord.Line.Speaker, record: CallRecord): String = when (speaker) {
    CallRecord.Line.Speaker.RECEPTIONIST -> record.contactName
    CallRecord.Line.Speaker.AGENT -> if (record.mode == CallMode.LIVE) "Ishara (voice)" else "Ishara for you"
    CallRecord.Line.Speaker.USER -> "You"
}

private fun formatDate(epochSeconds: Double): String =
    DateFormat.getDateTimeInstance(DateFormat.MEDIUM, DateFormat.SHORT).format(Date((epochSeconds * 1000).toLong()))
