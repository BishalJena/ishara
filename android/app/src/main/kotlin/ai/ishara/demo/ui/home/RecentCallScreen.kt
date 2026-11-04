package ai.ishara.demo.ui.home

import ai.ishara.demo.core.call.CallNotes
import ai.ishara.demo.core.call.CaptionSpeaker
import ai.ishara.demo.models.CallRecord
import ai.ishara.demo.ui.notes.NotesModel
import ai.ishara.demo.ui.steer.SteerType
import ai.ishara.demo.ui.steer.steerColors
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.outlined.HelpOutline
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.outlined.Delete
import androidx.compose.material.icons.outlined.Info
import androidx.compose.material3.CenterAlignedTopAppBar
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

/**
 * A saved call, read only (port of iOS `RecentCallView`): its notes when they were loaded,
 * otherwise the captions the call screen showed. [record] comes from the history, so notes that
 * arrive while it is open (Bolna's late summary) show up; it is null once the call is deleted.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RecentCallScreen(record: CallRecord?, onBack: () -> Unit, onDelete: () -> Unit) {
    val colors = steerColors()
    Column(Modifier.fillMaxSize().background(colors.groupedBackground)) {
        CenterAlignedTopAppBar(
            title = { Text(record?.let { recentCallDate(it.date) }.orEmpty(), style = SteerType.headline) },
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
        Column(
            modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(22.dp),
        ) {
            val notes = record.notes
            if (notes != null) {
                NotesSections(notes, record.contactName)
            } else {
                Section("Call with ${record.contactName}") {
                    OutcomeLabel(record.outcomeText(), Icons.Outlined.Info)
                }
                Section("Captions") {
                    if (record.captions.isEmpty()) Text("No captions in this call.", style = SteerType.body, color = colors.secondary)
                    record.captions.forEachIndexed { index, line ->
                        if (index > 0) Divider()
                        TranscriptRow(speakerName(line.speaker), line.text, isAgent = line.speaker == CallRecord.Line.Speaker.AGENT)
                    }
                }
            }
        }
    }
}

/** iOS `NotesSections`: the notes of a saved call. */
@Composable
private fun NotesSections(notes: CallNotes, contactName: String) {
    val colors = steerColors()
    Section("Call with $contactName") {
        OutcomeLabel(
            NotesModel.describe(notes.outcome, notes.ready),
            if (notes.outcome == "booked") Icons.Filled.CheckCircle else Icons.Outlined.Info,
        )
    }
    if (notes.summary.isNotEmpty()) {
        Section("What happened") {
            notes.summary.forEachIndexed { index, line ->
                if (index > 0) Divider()
                Text(line, style = SteerType.body, color = colors.primary)
            }
        }
    }
    if (notes.openQuestions.isNotEmpty()) {
        Section("Still open") {
            notes.openQuestions.forEachIndexed { index, question ->
                if (index > 0) Divider()
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Icon(Icons.AutoMirrored.Outlined.HelpOutline, contentDescription = null, tint = colors.orange, modifier = Modifier.size(20.dp))
                    Text(question, style = SteerType.body, color = colors.orange)
                }
            }
        }
    }
    notes.brief?.let { brief -> Section("The brief you approved") { Text(brief, style = SteerType.body, color = colors.primary) } }
    Section("Transcript") {
        if (notes.transcript.isEmpty()) Text("Nothing was heard on the call.", style = SteerType.body, color = colors.secondary)
        notes.transcript.forEachIndexed { index, entry ->
            if (index > 0) Divider()
            val isAgent = entry.speaker == CaptionSpeaker.AGENT
            TranscriptRow(if (isAgent) "Agent (for you)" else "They said", entry.text, isAgent)
        }
    }
    notes.bolnaSummary?.let { summary ->
        Section(
            "Automatic summary",
            footer = "Written by the call service's AI. It can be wrong; the transcript is what was said.",
        ) {
            Text(summary, style = SteerType.body, color = colors.primary, modifier = Modifier.testTag("notes.bolnaSummary"))
        }
    }
}

/** An inset grouped list section: a small capital header, the rows in a card, an optional footer. */
@Composable
private fun Section(header: String, footer: String? = null, content: @Composable ColumnScope.() -> Unit) {
    val colors = steerColors()
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(header.uppercase(), style = SteerType.footnote, color = colors.secondary, modifier = Modifier.padding(horizontal = 16.dp))
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(10.dp))
                .background(colors.secondaryGroupedBackground)
                .padding(horizontal = 16.dp, vertical = 11.dp),
            verticalArrangement = Arrangement.spacedBy(11.dp),
            content = content,
        )
        footer?.let { Text(it, style = SteerType.footnote, color = colors.secondary, modifier = Modifier.padding(horizontal = 16.dp)) }
    }
}

@Composable
private fun Divider() {
    HorizontalDivider(color = steerColors().separator, thickness = 0.5.dp)
}

@Composable
private fun OutcomeLabel(text: String, icon: ImageVector) {
    val colors = steerColors()
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        // Read as one element, so the icon isn't announced on its own.
        modifier = Modifier.testTag("notes.outcome").semantics(mergeDescendants = true) {},
    ) {
        Icon(icon, contentDescription = null, tint = colors.blue, modifier = Modifier.size(20.dp))
        Text(text, style = SteerType.headline, color = colors.primary)
    }
}

@Composable
private fun TranscriptRow(speaker: String, text: String, isAgent: Boolean) {
    val colors = steerColors()
    Column(verticalArrangement = Arrangement.spacedBy(2.dp), modifier = Modifier.semantics(mergeDescendants = true) {}) {
        Text(speaker, style = SteerType.caption, fontWeight = FontWeight.SemiBold, color = if (isAgent) colors.blue else colors.secondary)
        Text(text, style = SteerType.body, color = colors.primary)
    }
}

/** The call screen's names for who spoke (`CaptionHistory`). */
private fun speakerName(speaker: CallRecord.Line.Speaker): String = when (speaker) {
    CallRecord.Line.Speaker.RECEPTIONIST -> "Receptionist"
    CallRecord.Line.Speaker.AGENT -> "Ishara (voice)"
    CallRecord.Line.Speaker.USER -> "You"
}
