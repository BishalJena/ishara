package ai.ishara.demo.ui.home

import ai.ishara.demo.models.CallRecord
import ai.ishara.demo.ui.components.FormSection
import ai.ishara.demo.ui.notes.NotesRow
import ai.ishara.demo.ui.notes.NotesRows
import ai.ishara.demo.ui.notes.NotesSections
import ai.ishara.demo.ui.notes.OutcomeLabel
import ai.ishara.demo.ui.notes.TranscriptRow
import ai.ishara.demo.ui.steer.SteerType
import ai.ishara.demo.ui.steer.steerColors
import ai.ishara.demo.ui.theme.IsharaType
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.outlined.Delete
import androidx.compose.material3.CenterAlignedTopAppBar
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

/**
 * A saved call, read only (port of iOS `RecentCallView`): its notes when they were loaded,
 * otherwise the captions the call screen showed. [record] comes from the history, so notes that
 * arrive while it is open (Bolna's late summary) show up; it is null once the call is deleted.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RecentCallScreen(record: CallRecord?, onBack: () -> Unit, onDelete: () -> Unit, onRefresh: suspend (CallRecord) -> Unit = {}) {
    LaunchedEffect(record?.id) { record?.let { onRefresh(it) } }
    val colors = steerColors()
    Column(Modifier.fillMaxSize().background(colors.groupedBackground)) {
        CenterAlignedTopAppBar(
            title = { Text("Call summary", style = SteerType.headline) },
            navigationIcon = {
                IconButton(onClick = onBack, modifier = Modifier.testTag("recentCall.back")) {
                    Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                }
            },
            actions = {
                if (record != null) {
                    IconButton(onClick = onDelete, modifier = Modifier.testTag("recentCall.delete")) {
                        Icon(Icons.Outlined.Delete, contentDescription = "Delete this call")
                    }
                }
            },
            // AppRoot already keeps the screen clear of the system bars.
            windowInsets = WindowInsets(0),
            colors = TopAppBarDefaults.topAppBarColors(
                containerColor = colors.groupedBackground,
                titleContentColor = colors.primary,
                navigationIconContentColor = colors.blue,
                actionIconContentColor = colors.red,
            ),
        )
        if (record == null) return@Column
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(vertical = 8.dp)) {
            val notes = record.notes
            if (notes != null) {
                NotesSections(notes, record.contactName)
            } else {
                Column(verticalArrangement = Arrangement.spacedBy(24.dp)) {
                    FormSection(header = "Call with ${record.contactName}") {
                        NotesRow { OutcomeLabel(record.outcomeText(), booked = false) }
                    }
                    FormSection(header = "Captions") {
                        if (record.captions.isEmpty()) {
                            NotesRow { Text("No captions in this call.", style = IsharaType.body, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                        }
                        NotesRows(record.captions) { line ->
                            TranscriptRow(speakerName(line.speaker), line.text, isAgent = line.speaker == CallRecord.Line.Speaker.AGENT)
                        }
                    }
                }
            }
        }
    }
}

/** The call screen's names for who spoke (`CaptionHistory`). */
private fun speakerName(speaker: CallRecord.Line.Speaker): String = when (speaker) {
    CallRecord.Line.Speaker.RECEPTIONIST -> "Receptionist"
    CallRecord.Line.Speaker.AGENT -> "Ishara (voice)"
    CallRecord.Line.Speaker.USER -> "You"
}
