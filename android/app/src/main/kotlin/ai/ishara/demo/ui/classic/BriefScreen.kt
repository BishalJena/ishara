package ai.ishara.demo.ui.classic

import ai.ishara.demo.models.CallSetup
import ai.ishara.demo.ui.components.BigActionButton
import ai.ishara.demo.ui.components.CameraCard
import ai.ishara.demo.ui.components.CandidateTile
import ai.ishara.demo.ui.components.FramingHint
import ai.ishara.demo.ui.components.ReplayMenu
import ai.ishara.demo.ui.theme.IsharaColors
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch

/**
 * D9 step 1: sign or tap what's needed, add what the agent may share, build the brief and
 * approve it by starting the call. The app root runs [model] while shown. Placeholder layout;
 * the next phase ports iOS `BriefView` here, keeping these parameters.
 */
@Composable
fun BriefScreen(model: BriefModel, modeDescription: String, onApprove: (CallSetup) -> Unit, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        TextButton(onClick = onBack) { Text("Back") }
        Text("Sign what you need", style = MaterialTheme.typography.headlineSmall)
        CameraCard(camera = model.recognition.camera, state = model.cameraState)
        ReplayMenu(model.recognition.replayOptions, model.recognition::replay)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            BriefModel.suggestions.forEach { sign ->
                FilterChip(
                    selected = sign in model.chips,
                    onClick = { if (sign in model.chips) model.remove(sign) else model.add(sign) },
                    label = { Text(sign.wire) },
                    modifier = Modifier.testTag("brief.add.${sign.wire}"),
                )
            }
        }
        model.candidate?.let { CandidateTile(it, model::acceptCandidate, model::dismissCandidate) }
        if (model.lastSignUnsure) Text("That sign wasn't clear. Sign it again.", modifier = Modifier.testTag("brief.unsure"))
        if (model.showsFramingHint) FramingHint()
        OutlinedTextField(model.name, { model.name = it }, label = { Text("Your name") }, modifier = Modifier.fillMaxWidth().testTag("brief.name"))
        OutlinedTextField(
            model.callback,
            { model.callback = it },
            label = { Text("Callback number (optional)") },
            modifier = Modifier.fillMaxWidth().testTag("brief.callback"),
        )
        OutlinedTextField(
            model.reason,
            { model.reason = it },
            label = { Text("Reason, if asked (optional)") },
            modifier = Modifier.fillMaxWidth().testTag("brief.reason"),
        )
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Stay on the call to answer questions", modifier = Modifier.weight(1f))
            Switch(model.attended, { model.attended = it }, modifier = Modifier.testTag("brief.attended"))
        }
        model.failure?.let { Text(it, color = IsharaColors.Red) }
        model.brief?.let { Text(it.text, modifier = Modifier.testTag("brief.text")) }
        if (modeDescription.isNotEmpty()) Text(modeDescription, style = MaterialTheme.typography.bodySmall)
        Column(modifier = Modifier.testTag("brief.actionBar"), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            val approved = model.approvedSetup
            if (approved != null) {
                BigActionButton("Start the call", MaterialTheme.colorScheme.primary, { onApprove(approved) }, Modifier.testTag("brief.approve"))
            } else {
                OutlinedButton(
                    onClick = { scope.launch { model.prepare() } },
                    enabled = model.canPrepare,
                    modifier = Modifier.fillMaxWidth().testTag("brief.prepare"),
                ) { Text("Show the brief") }
            }
        }
    }
}
