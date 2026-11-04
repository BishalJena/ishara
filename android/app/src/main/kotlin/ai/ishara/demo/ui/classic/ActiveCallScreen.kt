package ai.ishara.demo.ui.classic

import ai.ishara.demo.call.ActiveCallStage
import ai.ishara.demo.call.ActiveCallViewModel
import ai.ishara.demo.ui.components.AskCard
import ai.ishara.demo.ui.components.BigActionButton
import ai.ishara.demo.ui.components.CallEndedPanel
import ai.ishara.demo.ui.components.CallErrorBanner
import ai.ishara.demo.ui.components.CallStatusBar
import ai.ishara.demo.ui.components.CameraCard
import ai.ishara.demo.ui.components.CandidateTile
import ai.ishara.demo.ui.components.CaptionHistory
import ai.ishara.demo.ui.components.ChipRow
import ai.ishara.demo.ui.components.ConnectionLostPanel
import ai.ishara.demo.ui.components.DeliveryBanner
import ai.ishara.demo.ui.components.DraftCard
import ai.ishara.demo.ui.components.FramingHint
import ai.ishara.demo.ui.components.QuickReplyBar
import ai.ishara.demo.ui.components.ReplayMenu
import ai.ishara.demo.ui.components.StopTooLateBanner
import ai.ishara.demo.ui.theme.IsharaColors
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

/**
 * Screens 3 and 4: signing a reply, then speaking it; also the ended state. The app root runs
 * [model] while this is shown. Placeholder layout; the next phase ports iOS `ActiveCallView`
 * (with `SigningPanel`, `SpeakingPanel` and the action bar) here, keeping these parameters.
 * [onShowNotes] is set for a delegated (D9) call.
 */
@Composable
fun ActiveCallScreen(model: ActiveCallViewModel, onLeave: () -> Unit, onShowNotes: (() -> Unit)?) {
    val stage = ActiveCallStage.of(model)
    Column(modifier = Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        CallStatusBar(model.setup.contact.name, model.phase, model.isSpeaking, model.connectedAt, onEnd = model::end)
        Column(
            modifier = Modifier.weight(1f).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            CaptionHistory(model.captions, Modifier.fillMaxWidth().heightIn(min = 80.dp, max = 220.dp), isCallOver = model.isCallOver)
            if (model.watchesSigns && !model.isCallOver) {
                CameraCard(camera = model.recognition.camera, state = model.cameraState)
                ReplayMenu(model.recognition.replayOptions, model.recognition::replay)
            }
            model.openQuestion?.let { AskCard(it, model::answer) }
            ChipRow(model.chips, model::removeChip)
            model.candidate?.let { CandidateTile(it, model::acceptCandidate, model::dismissCandidate) }
            if (model.showsFramingHint) FramingHint()
            if (model.showsDeliveryResult) DeliveryBanner(model.delivery)
            if (model.isStopTooLate) StopTooLateBanner()
            model.errorMessage?.let { CallErrorBanner(it) }
            when (stage) {
                ActiveCallStage.Signing -> if (model.isDelegated) {
                    Text(
                        if (model.isAttended) "Ishara runs the call. Answer its questions by signing or tapping." else "Ishara runs the call and calls back with the result.",
                        modifier = Modifier.testTag("call.delegatedNote"),
                    )
                } else {
                    DraftCard(model.draft, isComposing = model.isComposing)
                }
                is ActiveCallStage.Speaking -> Text(
                    "Speaking: \u201C${stage.text}\u201D",
                    style = MaterialTheme.typography.titleLarge,
                    modifier = Modifier.testTag("call.speaking"),
                )
                is ActiveCallStage.ConnectionLost -> ConnectionLostPanel(stage.notice, stage.isReconnecting)
                is ActiveCallStage.Ended -> CallEndedPanel(stage.reason)
            }
        }
        ActionBar(model, stage, onLeave, onShowNotes)
    }
}

@Composable
private fun ActionBar(model: ActiveCallViewModel, stage: ActiveCallStage, onLeave: () -> Unit, onShowNotes: (() -> Unit)?) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.testTag("call.actionBar")) {
        when (stage) {
            is ActiveCallStage.Ended, is ActiveCallStage.ConnectionLost -> if (model.isCallOver) {
                if (onShowNotes != null) {
                    BigActionButton("See the notes", MaterialTheme.colorScheme.primary, onShowNotes, Modifier.testTag("call.notes"))
                }
                OutlinedButton(onClick = onLeave, modifier = Modifier.fillMaxWidth().testTag("call.backHome")) { Text("Back to Home") }
            }
            is ActiveCallStage.Speaking -> BigActionButton(
                "STOP",
                IsharaColors.Red,
                model::stop,
                Modifier.testTag("call.stop"),
                enabled = !model.isStopRequested,
            )
            ActiveCallStage.Signing -> if (!model.isDelegated) {
                QuickReplyBar(model::choose, enabled = model.canUseQuickReplies)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(
                        onClick = model::clear,
                        enabled = model.chips.isNotEmpty() || model.draft != null,
                        modifier = Modifier.heightIn(min = 64.dp).testTag("call.clear"),
                    ) { Text("Clear") }
                    BigActionButton(
                        "SEND",
                        IsharaColors.Green,
                        model::send,
                        Modifier.weight(1f).testTag("call.send"),
                        enabled = model.canSend,
                        foreground = Color.Black,
                    )
                }
            }
        }
    }
}
