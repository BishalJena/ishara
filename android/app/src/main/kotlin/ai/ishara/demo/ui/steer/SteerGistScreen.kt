package ai.ishara.demo.ui.steer

import ai.ishara.demo.core.call.CallNotes
import ai.ishara.demo.core.call.CaptionSpeaker
import ai.ishara.demo.ui.notes.NotesModel
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.FormatListBulleted
import androidx.compose.material.icons.automirrored.filled.Chat
import androidx.compose.material.icons.automirrored.filled.Notes
import androidx.compose.material.icons.automirrored.filled.PhoneCallback
import androidx.compose.material.icons.automirrored.filled.PhoneForwarded
import androidx.compose.material.icons.filled.Bookmark
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.FormatQuote
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Keyboard
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.PhoneDisabled
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.CenterAlignedTopAppBar
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch

/**
 * The gist after a steer call (port of iOS `SteerGistView`): the outcome in one line, what was
 * decided and shared, the follow-ups the receptionist asked for, how much the user stepped in,
 * and the transcript. Every detail comes from the backend's notes, which quote the transcript.
 * [model] is already polling.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SteerGistScreen(model: NotesModel, onDone: () -> Unit, onCallAgain: () -> Unit) {
    val colors = steerColors()
    val scope = rememberCoroutineScope()
    Column(Modifier.fillMaxSize().background(colors.groupedBackground)) {
        CenterAlignedTopAppBar(
            title = { Text("Call with ${model.contactName}", style = SteerType.headline, maxLines = 1) },
            actions = {
                IconButton(
                    onClick = { scope.launch { model.refresh() } },
                    enabled = !model.isLoading,
                    modifier = Modifier.testTag("notes.refresh"),
                ) {
                    Icon(Icons.Filled.Refresh, contentDescription = "Refresh")
                }
            },
            // AppRoot already keeps the screen clear of the system bars.
            windowInsets = WindowInsets(0),
            colors = TopAppBarDefaults.topAppBarColors(
                containerColor = colors.groupedBackground,
                titleContentColor = colors.primary,
                actionIconContentColor = MaterialTheme.colorScheme.primary,
            ),
        )
        Column(
            verticalArrangement = Arrangement.spacedBy(22.dp),
            modifier = Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState()).padding(20.dp),
        ) {
            val notes = model.notes
            val failure = model.failure
            when {
                notes != null -> {
                    Outcome(notes)
                    if (notes.summary.isNotEmpty()) Summary(notes.summary)
                    if (notes.followUps.isNotEmpty()) FollowUps(notes.followUps)
                    notes.bolnaSummary?.let { bolna ->
                        Card("Call summary", Icons.Filled.FormatQuote) {
                            Text(bolna, style = SteerType.body, color = colors.primary, modifier = Modifier.testTag("notes.bolnaSummary"))
                        }
                    }
                    Transcript(notes, model.contactName)
                }
                failure != null -> Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    modifier = Modifier.testTag("notes.failure"),
                ) {
                    Icon(Icons.Filled.Warning, contentDescription = null, tint = colors.red)
                    Text(failure, style = SteerType.body, color = colors.red)
                }
                else -> Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    CircularProgressIndicator()
                    Text("Wrapping up the call…", style = SteerType.body, color = colors.secondary)
                }
            }
        }
        // The way out is the one big button at the bottom, where the thumb already is.
        Row(
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            modifier = Modifier
                .fillMaxWidth()
                .background(colors.bar)
                .padding(start = 20.dp, end = 20.dp, top = 10.dp, bottom = 6.dp),
        ) {
            OutlinedButton(
                onClick = onCallAgain,
                contentPadding = PaddingValues(vertical = 12.dp),
                modifier = Modifier.weight(1f).testTag("notes.callAgain"),
            ) {
                Icon(Icons.AutoMirrored.Filled.PhoneForwarded, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(6.dp))
                Text("Call again")
            }
            Button(
                onClick = onDone,
                contentPadding = PaddingValues(vertical = 12.dp),
                modifier = Modifier.weight(1f).testTag("notes.done"),
            ) {
                Text("Done", style = SteerType.headline)
            }
        }
    }
}

@Composable
private fun Outcome(notes: CallNotes) {
    val colors = steerColors()
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        val booked = notes.outcome == "booked"
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            modifier = Modifier.testTag("notes.outcome").semantics(mergeDescendants = true) {},
        ) {
            Icon(outcomeIcon(notes.outcome), contentDescription = null, tint = if (booked) colors.green else colors.primary, modifier = Modifier.size(26.dp))
            Text(
                NotesModel.describe(notes.outcome, notes.ready),
                style = SteerType.title2,
                fontWeight = FontWeight.Bold,
                color = if (booked) colors.green else colors.primary,
            )
        }
        Text(steppedInText(notes.steppedIn), style = SteerType.subheadline, color = colors.secondary, modifier = Modifier.testTag("notes.steppedIn"))
    }
}

private fun outcomeIcon(outcome: String?): ImageVector = when (outcome) {
    "booked" -> Icons.Filled.CheckCircle
    "no_answer" -> Icons.Filled.PhoneDisabled
    "callback" -> Icons.AutoMirrored.Filled.PhoneCallback
    else -> Icons.Filled.Info
}

/** iOS `SteerGistView.steppedInText`. */
fun steppedInText(steppedIn: Int): String = when (steppedIn) {
    0 -> "Ishara handled the whole call from what you wrote."
    1 -> "You stepped in once; Ishara handled the rest."
    2 -> "You stepped in twice; Ishara handled the rest."
    else -> "You stepped in $steppedIn times; Ishara handled the rest."
}

@Composable
private fun Summary(lines: List<String>) {
    val colors = steerColors()
    Card("The gist", Icons.AutoMirrored.Filled.FormatListBulleted, Modifier.testTag("notes.summary")) {
        lines.forEach { line ->
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Icon(
                    if (line.startsWith("You")) Icons.Filled.Keyboard else Icons.AutoMirrored.Filled.Chat,
                    contentDescription = null,
                    tint = colors.secondary,
                    modifier = Modifier.padding(top = 3.dp).size(14.dp),
                )
                Text(line, style = SteerType.body, color = colors.primary)
            }
        }
    }
}

@Composable
private fun FollowUps(followUps: List<String>) {
    val colors = steerColors()
    Column(
        verticalArrangement = Arrangement.spacedBy(10.dp),
        modifier = Modifier
            .fillMaxWidth()
            .background(colors.orange.copy(alpha = 0.12f), RoundedCornerShape(20.dp))
            .padding(16.dp)
            .testTag("notes.followUps")
            .semantics(mergeDescendants = true) {},
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Icon(Icons.Filled.Bookmark, contentDescription = null, tint = colors.orange, modifier = Modifier.size(18.dp))
            Text(
                if (followUps.size == 1) "1 follow-up" else "${followUps.size} follow-ups",
                style = SteerType.headline,
                color = colors.orange,
            )
        }
        followUps.forEach { asked ->
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("They asked: \u201C$asked\u201D", style = SteerType.subheadline, fontWeight = FontWeight.SemiBold, color = colors.primary)
                Text(
                    "Ishara said you'd send it afterwards. It never guesses a detail you didn't give.",
                    style = SteerType.footnote,
                    color = colors.secondary,
                )
            }
        }
    }
}

/** The full transcript, folded away until asked for (SwiftUI `DisclosureGroup`). */
@Composable
private fun Transcript(notes: CallNotes, contactName: String) {
    val colors = steerColors()
    var expanded by rememberSaveable { mutableStateOf(false) }
    val chevron by animateFloatAsState(if (expanded) 0f else -90f, label = "chevron")
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(20.dp))
            .background(colors.secondaryGroupedBackground),
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            modifier = Modifier
                .fillMaxWidth()
                .clickable { expanded = !expanded }
                .padding(16.dp)
                .testTag("notes.transcriptToggle")
                .semantics(mergeDescendants = true) { stateDescription = if (expanded) "Expanded" else "Collapsed" },
        ) {
            Icon(Icons.AutoMirrored.Filled.Notes, contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(20.dp))
            Text("Full transcript (${notes.transcript.size} lines)", style = SteerType.headline, color = colors.primary, modifier = Modifier.weight(1f))
            Icon(
                Icons.Filled.KeyboardArrowDown,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.primary,
                modifier = Modifier.rotate(chevron),
            )
        }
        AnimatedVisibility(expanded) {
            Column(
                verticalArrangement = Arrangement.spacedBy(12.dp),
                modifier = Modifier.padding(start = 16.dp, end = 16.dp, bottom = 16.dp).testTag("notes.transcript"),
            ) {
                notes.transcript.forEach { entry ->
                    val isAgent = entry.speaker == CaptionSpeaker.AGENT
                    Column(verticalArrangement = Arrangement.spacedBy(2.dp), modifier = Modifier.semantics(mergeDescendants = true) {}) {
                        Text(
                            if (isAgent) "Ishara for you" else contactName,
                            style = SteerType.caption,
                            fontWeight = FontWeight.Bold,
                            color = if (isAgent) colors.purple else colors.secondary,
                        )
                        Text(entry.text, style = SteerType.subheadline, color = colors.primary)
                    }
                }
            }
        }
    }
}

@Composable
private fun Card(title: String, icon: ImageVector, modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    val colors = steerColors()
    Column(
        verticalArrangement = Arrangement.spacedBy(10.dp),
        modifier = modifier
            .fillMaxWidth()
            .background(colors.secondaryGroupedBackground, RoundedCornerShape(20.dp))
            .padding(16.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(20.dp))
            Text(title, style = SteerType.headline, color = colors.primary)
        }
        content()
    }
}
