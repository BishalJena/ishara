package ai.ishara.demo.ui.home

import ai.ishara.demo.core.call.CallMode
import ai.ishara.demo.models.CallHistory
import ai.ishara.demo.models.CallRecord
import ai.ishara.demo.ui.notes.NotesModel
import ai.ishara.demo.ui.steer.SteerType
import ai.ishara.demo.ui.steer.steerColors
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Phone
import androidx.compose.material.icons.filled.RecordVoiceOver
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.SwipeToDismissBox
import androidx.compose.material3.SwipeToDismissBoxValue
import androidx.compose.material3.Text
import androidx.compose.material3.rememberSwipeToDismissBoxState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.key
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import java.text.DateFormat
import java.util.Date

/**
 * Home: the calls kept on this phone, newest first (port of iOS `RecentCallsSection`). Tap one
 * to read it again; swipe it away to delete it. Hidden until there is a call (or a problem).
 */
@Composable
fun RecentCallsSection(history: CallHistory, onOpen: (recordId: String) -> Unit) {
    if (history.records.isEmpty() && history.problem == null) return
    val colors = steerColors()
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(
            "RECENT CALLS",
            style = SteerType.footnote,
            color = colors.secondary,
            modifier = Modifier.padding(horizontal = 16.dp),
        )
        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(colors.secondaryGroupedBackground)) {
            history.problem?.let { problem ->
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 11.dp).testTag("recentCalls.problem"),
                ) {
                    Icon(Icons.Filled.Warning, contentDescription = null, tint = colors.orange, modifier = Modifier.size(18.dp))
                    Text(problem, style = SteerType.body, color = colors.orange)
                }
            }
            history.records.forEachIndexed { index, record ->
                if (index > 0 || history.problem != null) {
                    HorizontalDivider(color = colors.separator, thickness = 0.5.dp, modifier = Modifier.padding(start = 16.dp))
                }
                key(record.id) { SwipeToDelete(onDelete = { history.delete(record.id) }) { RecentCallRow(record, onOpen) } }
            }
        }
        Text(
            "Kept on this phone only. Swipe left on a call to delete it.",
            style = SteerType.footnote,
            color = colors.secondary,
            modifier = Modifier.padding(horizontal = 16.dp),
        )
    }
}

@Composable
private fun SwipeToDelete(onDelete: () -> Unit, content: @Composable () -> Unit) {
    val colors = steerColors()
    val state = rememberSwipeToDismissBoxState()
    SwipeToDismissBox(
        state = state,
        enableDismissFromStartToEnd = false,
        onDismiss = { value -> if (value == SwipeToDismissBoxValue.EndToStart) onDelete() },
        backgroundContent = {
            Box(Modifier.fillMaxSize().background(colors.red).padding(horizontal = 20.dp), contentAlignment = Alignment.CenterEnd) {
                Icon(Icons.Filled.Delete, contentDescription = null, tint = Color.White)
            }
        },
        // TalkBack can't swipe a row; it offers Delete as an action instead.
        modifier = Modifier.semantics { customActions = listOf(CustomAccessibilityAction("Delete") { onDelete(); true }) },
    ) { content() }
}

@Composable
private fun RecentCallRow(record: CallRecord, onOpen: (String) -> Unit) {
    val colors = steerColors()
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        modifier = Modifier
            .fillMaxWidth()
            .background(colors.secondaryGroupedBackground)
            .clickable { onOpen(record.id) }
            .padding(horizontal = 16.dp, vertical = 10.dp)
            .testTag("recentCalls.row")
            .semantics(mergeDescendants = true) {},
    ) {
        Icon(
            if (record.mode == CallMode.DELEGATED) Icons.Filled.RecordVoiceOver else Icons.Filled.Phone,
            contentDescription = null,
            tint = colors.secondary,
            modifier = Modifier.size(20.dp),
        )
        Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(record.contactName, style = SteerType.headline, color = colors.primary)
            Text(record.outcomeText(), style = SteerType.subheadline, color = colors.primary)
            Text(recentCallDate(record.date, DateFormat.SHORT), style = SteerType.caption, color = colors.secondary)
        }
    }
}

/** The outcome in the notes' words, or what kind of call it was when there are no notes (iOS `CallRecord.outcomeText`). */
fun CallRecord.outcomeText(): String {
    notes?.let { return NotesModel.describe(it.outcome, it.ready) }
    return when (mode) {
        CallMode.LIVE -> "You signed the call"
        CallMode.DELEGATED -> "Call for me: the notes weren't loaded"
        CallMode.STEER -> "Ishara ran the call: the notes weren't loaded"
    }
}

/** A saved call's date and time, like iOS `.formatted(date: .abbreviated, time: .shortened)`. */
fun recentCallDate(epochSeconds: Double, dateStyle: Int = DateFormat.MEDIUM): String =
    DateFormat.getDateTimeInstance(dateStyle, DateFormat.SHORT).format(Date((epochSeconds * 1000).toLong()))
