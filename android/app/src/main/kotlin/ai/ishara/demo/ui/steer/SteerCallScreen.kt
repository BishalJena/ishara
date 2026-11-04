package ai.ishara.demo.ui.steer

import ai.ishara.demo.call.ActiveCallViewModel
import ai.ishara.demo.core.call.Caption
import ai.ishara.demo.ui.components.CallErrorBanner
import ai.ishara.demo.ui.components.InitialsAvatar
import ai.ishara.demo.ui.components.epochSeconds
import ai.ishara.demo.ui.theme.IsharaColors
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.delay

/**
 * The one call screen for steer calls: Ishara runs the call from the typed request; the user
 * watches the captions and steps in by typing (first) or signing. The app root runs [model].
 * Placeholder layout; the next phase ports iOS `SteerCallView` here (facts strip, cover line,
 * filling Send bar, signing panel, not-through tray), keeping these parameters and using
 * `SteerLogic.kt`.
 */
@Composable
fun SteerCallScreen(model: ActiveCallViewModel, onLeave: () -> Unit, onShowNotes: () -> Unit) {
    var typed by rememberSaveable { mutableStateOf("") }
    ReportPresence(model)
    // A call that got through goes on to its gist after a beat; one that didn't stays here.
    LaunchedEffect(model.isCallOver) {
        if (model.isCallOver && SteerCallText.notThrough(model) == null) {
            delay(2_000)
            onShowNotes()
        }
    }
    Column(modifier = Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            InitialsAvatar(model.setup.contact.name)
            Column(Modifier.weight(1f)) {
                Text(model.setup.contact.name, style = MaterialTheme.typography.titleLarge)
                Text(SteerCallText.timer(model.connectedAt, model.phase, now()), style = MaterialTheme.typography.bodySmall)
            }
            if (model.isCallOver) {
                Button(onClick = onShowNotes, modifier = Modifier.testTag("steer.gist")) { Text("Gist") }
            } else {
                Button(
                    onClick = model::end,
                    colors = ButtonDefaults.buttonColors(containerColor = IsharaColors.Red, contentColor = Color.White),
                    modifier = Modifier.testTag("steer.end"),
                ) { Text("End") }
            }
        }
        Text(SteerCallText.status(model, isSigning = false), modifier = Modifier.testTag("steer.status"))
        CallFacts.extract(model.captions.filter { it.speaker == Caption.Speaker.RECEPTIONIST }.map { it.text })
            .takeIf { it.isNotEmpty() }
            ?.let { facts -> Text(facts.joinToString(" · ") { it.text }, modifier = Modifier.testTag("steer.facts")) }
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            CoverLines.rows(model.captions).forEach { row ->
                Text("${speakerName(row.caption.speaker, model)}: ${row.caption.text}")
            }
            model.followUps.lastOrNull()?.let {
                Text("Saved as a follow-up: \u201C$it\u201D", color = IsharaColors.Orange, modifier = Modifier.testTag("steer.followUp"))
            }
        }
        model.errorMessage?.let { CallErrorBanner(it) }
        val problem = SteerCallText.notThrough(model)
        if (problem != null) {
            Column(modifier = Modifier.testTag("steer.notThrough"), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Didn't get through: $problem", color = IsharaColors.Red)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = onLeave) { Text("Back to the request") }
                    Button(onClick = onShowNotes) { Text("What happened") }
                }
            }
            return@Column
        }
        model.proposal?.let { proposal ->
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.weight(1f).testTag("steer.proposal")) {
                    Text(SteerCallText.proposalLabel(proposal, now()), style = MaterialTheme.typography.labelMedium)
                    Text(proposal.text)
                }
                Button(onClick = model::approveProposal, modifier = Modifier.testTag("steer.proposalAction")) { Text("↑") }
            }
        }
        if (!model.isCallOver) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = typed,
                    onValueChange = {
                        if (typed.isEmpty() && it.isNotEmpty()) model.beginSteppingIn()
                        typed = it
                    },
                    label = { Text("Type to step in…") },
                    modifier = Modifier.weight(1f).testTag("steer.field"),
                )
                Button(
                    onClick = {
                        model.say(typed.trim())
                        typed = ""
                    },
                    enabled = typed.isNotBlank(),
                    modifier = Modifier.testTag("steer.send"),
                ) { Text("↑") }
            }
            Text(
                "If you don't step in, Ishara keeps going. Nothing you type is spoken until you send it.",
                style = MaterialTheme.typography.bodySmall,
            )
        }
    }
}

/** The steer call hears whether the app is in front, so Ishara proposes lines only to a present user. */
@Composable
private fun ReportPresence(model: ActiveCallViewModel) {
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val hasStore = model.store != null
    DisposableEffect(lifecycle, hasStore) {
        model.setPresent(lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED))
        val observer = LifecycleEventObserver { _, _ -> model.setPresent(lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer) }
    }
}

@Composable
private fun now(): Double {
    val now by produceState(epochSeconds()) {
        while (true) {
            value = epochSeconds()
            delay(250)
        }
    }
    return now
}

private fun speakerName(speaker: Caption.Speaker, model: ActiveCallViewModel): String = when (speaker) {
    Caption.Speaker.RECEPTIONIST -> model.setup.contact.name
    Caption.Speaker.AGENT -> "Ishara for you"
    Caption.Speaker.USER -> "You"
}
