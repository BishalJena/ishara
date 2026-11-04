package ai.ishara.demo.ui.classic

import ai.ishara.demo.core.call.Brief
import ai.ishara.demo.core.call.Chip
import ai.ishara.demo.models.CallSetup
import ai.ishara.demo.models.title
import ai.ishara.demo.models.wire
import ai.ishara.demo.ui.components.BigActionButton
import ai.ishara.demo.ui.components.BorderedButton
import ai.ishara.demo.ui.components.BottomBar
import ai.ishara.demo.ui.components.CallingNumberNote
import ai.ishara.demo.ui.components.CameraCard
import ai.ishara.demo.ui.components.CandidateTile
import ai.ishara.demo.ui.components.ChipView
import ai.ishara.demo.ui.components.FramingHint
import ai.ishara.demo.ui.components.IconLabel
import ai.ishara.demo.ui.components.LargeTitle
import ai.ishara.demo.ui.components.ReplayMenu
import ai.ishara.demo.ui.components.TopBar
import ai.ishara.demo.ui.components.WarningLabel
import ai.ishara.demo.ui.theme.IsharaColors
import ai.ishara.demo.ui.theme.IsharaType
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.relocation.BringIntoViewRequester
import androidx.compose.foundation.relocation.bringIntoViewRequester
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Phone
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch

/**
 * "Call for me" (decision D9, iOS `BriefView`): sign or tap what's needed, add what the agent
 * may share, read the brief and approve it once by starting the call. The app root runs
 * [model] while shown. Nothing is dialled until Approve.
 */
@Composable
fun BriefScreen(model: BriefModel, modeDescription: String, onApprove: (CallSetup) -> Unit, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    val briefInView = remember { BringIntoViewRequester() }
    val brief = model.brief
    // The brief is built below the request and the details: bring it up above Approve.
    LaunchedEffect(brief != null) {
        if (brief != null) briefInView.bringIntoView()
    }
    Column(Modifier.fillMaxSize()) {
        TopBar(leading = { TextButton(onClick = onBack, modifier = Modifier.testTag("brief.back")) { Text("Back", style = IsharaType.body) } })
        Column(
            modifier = Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(bottom = 16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            LargeTitle("Call for me")
            Column(Modifier.padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                SigningSection(model)
                DetailsSection(model)
                if (brief != null) {
                    Column(Modifier.bringIntoViewRequester(briefInView), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                        BriefCard(brief, model.setup.contact.name)
                        AttendedToggle(model)
                    }
                }
                model.failure?.let { WarningLabel(it, Modifier.testTag("brief.failure")) }
            }
        }
        BottomBar(Modifier.testTag("brief.actionBar")) {
            if (modeDescription.isNotEmpty()) {
                Text(modeDescription, style = IsharaType.footnote, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            CallingNumberNote()
            val approved = model.approvedSetup
            if (approved != null) {
                BigActionButton("Approve and call", IsharaColors.Green, { onApprove(approved) }, Modifier.testTag("brief.approve"), icon = Icons.Filled.Phone)
            } else if (model.isPreparing) {
                Box(
                    Modifier.fillMaxWidth().background(IsharaColors.Blue, RoundedCornerShape(16.dp)).padding(20.dp).testTag("brief.prepare"),
                    contentAlignment = Alignment.Center,
                ) { CircularProgressIndicator(Modifier.size(24.dp), color = Color.White, strokeWidth = 2.dp) }
            } else {
                BigActionButton(
                    "Prepare the request",
                    IsharaColors.Blue,
                    { scope.launch { model.prepare() } },
                    Modifier.testTag("brief.prepare"),
                    enabled = model.canPrepare,
                    icon = Icons.Filled.Search,
                )
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun SigningSection(model: BriefModel) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("Sign what you need", style = IsharaType.headline)
        Text(
            "For ${model.setup.purpose.title.lowercase()} at ${model.setup.contact.name}. Sign the day and time, for example TOMORROW, MORNING.",
            style = IsharaType.subheadline,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Box {
            CameraCard(camera = model.recognition.camera, state = model.cameraState)
            ReplayMenu(model.recognition.replayOptions, model.recognition::replay, Modifier.align(Alignment.BottomEnd).padding(10.dp))
        }
        if (model.showsFramingHint) {
            FramingHint()
        } else if (model.lastSignUnsure) {
            IconLabel(
                "That sign wasn't recognised. Sign it again, or tap it below.",
                Icons.Filled.Info,
                modifier = Modifier.semantics(mergeDescendants = true) {}.testTag("brief.unsure"),
                color = IsharaColors.Orange,
                style = IsharaType.subheadline,
            )
        }
        model.candidate?.let { CandidateTile(it, model::acceptCandidate, model::dismissCandidate) }
        if (model.chips.isNotEmpty()) {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                model.chips.forEach { sign -> ChipView(Chip.recognised(sign)) { model.remove(sign) } }
            }
        }
        val remaining = BriefModel.suggestions.filter { it !in model.chips }
        if (remaining.isNotEmpty()) {
            Text("Or tap:", style = IsharaType.footnote, color = MaterialTheme.colorScheme.onSurfaceVariant)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                remaining.forEach { sign ->
                    BorderedButton(onClick = { model.add(sign) }, modifier = Modifier.testTag("brief.add.${sign.wire}")) {
                        Text(sign.wire, style = IsharaType.body)
                    }
                }
            }
        }
    }
}

@Composable
private fun DetailsSection(model: BriefModel) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("What the agent may share", style = IsharaType.headline)
        BriefField(model.name, { model.name = it }, "Your name", "brief.name", KeyboardOptions(capitalization = KeyboardCapitalization.Words))
        BriefField(model.callback, { model.callback = it }, "Callback number (optional)", "brief.callback", KeyboardOptions(keyboardType = KeyboardType.Phone))
        BriefField(
            model.reason,
            { model.reason = it },
            "Reason, if they ask (optional)",
            "brief.reason",
            KeyboardOptions(capitalization = KeyboardCapitalization.Sentences),
            singleLine = false,
        )
        Text("Nothing else about you is ever said.", style = IsharaType.footnote, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

/** iOS `.textFieldStyle(.roundedBorder)`: the hint inside the field, no floating label. */
@Composable
private fun BriefField(
    value: String,
    onValueChange: (String) -> Unit,
    hint: String,
    tag: String,
    keyboard: KeyboardOptions,
    singleLine: Boolean = true,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        placeholder = { Text(hint, style = IsharaType.body) },
        textStyle = IsharaType.body,
        singleLine = singleLine,
        keyboardOptions = keyboard,
        shape = RoundedCornerShape(8.dp),
        modifier = Modifier.fillMaxWidth().testTag(tag),
    )
}

@Composable
private fun AttendedToggle(model: BriefModel) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .toggleable(value = model.attended, role = Role.Switch) { model.attended = it }
            .testTag("brief.attended"),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text("I'll stay and answer questions", style = IsharaType.body)
            Text(
                if (model.attended) {
                    "The agent pauses and asks you here when a decision is yours."
                } else {
                    "The agent says it will call back instead of deciding for you."
                },
                style = IsharaType.footnote,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Switch(
            checked = model.attended,
            onCheckedChange = null,
            colors = SwitchDefaults.colors(checkedTrackColor = IsharaColors.Green, checkedThumbColor = Color.White, checkedBorderColor = IsharaColors.Green),
        )
    }
}

/** The brief exactly as the agent will pursue it. */
@Composable
fun BriefCard(brief: Brief, contactName: String, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(IsharaColors.Blue.copy(alpha = 0.1f), RoundedCornerShape(16.dp))
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        IconLabel("The agent follows only this brief with $contactName", Icons.Filled.Check, style = IsharaType.headline)
        Text(brief.text, style = IsharaType.body, modifier = Modifier.testTag("brief.text"))
    }
}
