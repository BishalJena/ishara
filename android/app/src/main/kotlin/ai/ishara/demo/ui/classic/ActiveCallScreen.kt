package ai.ishara.demo.ui.classic

import ai.ishara.demo.call.ActiveCallStage
import ai.ishara.demo.call.ActiveCallViewModel
import ai.ishara.demo.call.ActiveCallViewModel.Delivery
import ai.ishara.demo.call.ActiveCallViewModel.EndReason
import ai.ishara.demo.ui.components.AskCard
import ai.ishara.demo.ui.components.BottomBar
import ai.ishara.demo.ui.components.CallErrorBanner
import ai.ishara.demo.ui.components.CallStatusBar
import ai.ishara.demo.ui.components.CameraVideoRow
import ai.ishara.demo.ui.components.CandidateTile
import ai.ishara.demo.ui.components.CantSeeYouNotice
import ai.ishara.demo.ui.components.CaptionHistory
import ai.ishara.demo.ui.components.ChipRow
import ai.ishara.demo.ui.components.ConnectionLostPanel
import ai.ishara.demo.ui.components.DeliveryBanner
import ai.ishara.demo.ui.components.DestructiveButton
import ai.ishara.demo.ui.components.DraftCard
import ai.ishara.demo.ui.components.FramingHint
import ai.ishara.demo.ui.components.IconLabel
import ai.ishara.demo.ui.components.IsharaTextButton
import ai.ishara.demo.ui.components.PinnedSentence
import ai.ishara.demo.ui.components.PrimaryButton
import ai.ishara.demo.ui.components.QuickReplyBar
import ai.ishara.demo.ui.components.ReplayMenu
import ai.ishara.demo.ui.components.StopTooLateBanner
import ai.ishara.demo.ui.components.TonalButton
import ai.ishara.demo.ui.components.WarningLabel
import ai.ishara.demo.ui.theme.IsharaColors
import ai.ishara.demo.ui.theme.IsharaType
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.relocation.BringIntoViewRequester
import androidx.compose.foundation.relocation.bringIntoViewRequester
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.Call
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.path
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

/**
 * Screens 3 and 4 (iOS `ActiveCallView`): signing a reply, then speaking it; also the lost
 * connection and the ended call. The app root runs [model] while this is shown. [onShowNotes]
 * is set for a delegated (D9) call.
 *
 * The sentence SEND or STOP acts on lives in the pinned action bar right above its button, so
 * it can never scroll away or hide behind it at any text size; the captions give up height at
 * large text sizes so the chips stay reachable (see [CallLayout]). While the user may sign, the
 * live video sits under the captions with the panel beside it. Once the call is over the
 * transcript fills the screen.
 */
@Composable
fun ActiveCallScreen(model: ActiveCallViewModel, onLeave: () -> Unit, onShowNotes: (() -> Unit)?) {
    val stage = ActiveCallStage.of(model)
    val density = LocalDensity.current
    // Height of the action bar. It doesn't depend on the caption box, so sizing the captions
    // from it (and the screen) can't feed back into a layout loop.
    var actionBarHeight by remember { mutableStateOf<Dp?>(null) }
    val panelScroll = rememberScrollState()
    val chipsInView = remember { BringIntoViewRequester() }
    val bannerInView = remember { BringIntoViewRequester() }
    val showsDeliveryBanner = showsDeliveryBanner(model)

    // Keep the newest thing in the panel in view: the result of the last SEND when shown,
    // otherwise the chips (a wrong one must be removable before SEND).
    suspend fun scrollToNewest() {
        if (showsDeliveryBanner) bannerInView.bringIntoView() else chipsInView.bringIntoView()
    }
    LaunchedEffect(model.chips) { chipsInView.bringIntoView() }
    LaunchedEffect(actionBarHeight) { scrollToNewest() }
    LaunchedEffect(showsDeliveryBanner, model.delivery) { if (showsDeliveryBanner) bannerInView.bringIntoView() }

    BoxWithConstraints(Modifier.fillMaxSize()) {
        val layout = CallLayout(screenHeight = maxHeight, actionBarHeight = actionBarHeight)
        Column(Modifier.fillMaxSize()) {
            Column(
                modifier = Modifier.weight(1f).padding(start = 16.dp, end = 16.dp, top = 8.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                CallStatusBar(
                    model.setup.contact.name,
                    model.phase,
                    model.isSpeaking,
                    model.connectedAt,
                    onEnd = model::end,
                )
                if (stage is ActiveCallStage.Ended) {
                    EndedTranscript(model, stage.reason, Modifier.weight(1f))
                } else {
                    CaptionHistory(model.captions, Modifier.fillMaxWidth().weight(1f))
                    val panel = @Composable { modifier: Modifier ->
                        Column(modifier.heightIn(max = layout.panelMaxHeight).verticalScroll(panelScroll)) {
                            when (stage) {
                                is ActiveCallStage.ConnectionLost -> ConnectionLostPanel(stage.notice, stage.isReconnecting)
                                is ActiveCallStage.Speaking -> SpeakingPanel(model)
                                ActiveCallStage.Signing -> SigningPanel(model, chipsInView, bannerInView)
                                is ActiveCallStage.Ended -> Unit
                            }
                            Spacer(Modifier.height(8.dp))
                        }
                    }
                    // The same video through signing, speaking and a dropped connection, so it never jumps.
                    if (model.watchesSigns && !model.isCallOver) {
                        CameraVideoRow(
                            model.recognition.camera,
                            model.cameraState,
                            videoTag = "call.camera",
                            modifier = Modifier.padding(bottom = 8.dp),
                            maxVideoHeight = layout.panelMaxHeight,
                            side = panel,
                        )
                    } else {
                        panel(Modifier.fillMaxWidth())
                    }
                }
            }
            BottomBar(
                Modifier
                    .onSizeChanged { actionBarHeight = with(density) { it.height.toDp() } }
                    .testTag("call.actionBar"),
            ) {
                if (model.isDelegated) {
                    DelegatedBar(model, stage, layout, onLeave, onShowNotes)
                } else {
                    LiveBar(model, stage, layout.sentenceMaxHeight, onLeave)
                }
            }
        }
    }
}

/**
 * The call screen's sizes: the room for the pinned sentence, and for the panel under the
 * captions. The captions take whatever the panel leaves, so they fill the screen when there is
 * little to show and give up space at large text sizes so the chips stay reachable.
 */
private class CallLayout(private val screenHeight: Dp, private val actionBarHeight: Dp?) {
    /** Room for the pinned sentence; past this it scrolls inside its card. */
    val sentenceMaxHeight: Dp get() = screenHeight * 0.55f

    /** The panel (chips, banners) scrolls inside this, leaving the captions at least the rest. */
    val panelMaxHeight: Dp get() = (screenHeight - (actionBarHeight ?: 0.dp)) * 0.55f
}

private fun showsDeliveryBanner(model: ActiveCallViewModel): Boolean {
    if (model.isDelegated || !model.showsDeliveryResult) return false
    return when (model.delivery) {
        Delivery.Delivered, Delivery.DeliveredDespiteStop, is Delivery.NotDelivered, is Delivery.Stopped -> true
        Delivery.Idle, is Delivery.Speaking -> false
    }
}

/**
 * The call is over: the read-only transcript takes the screen (the status bar already says
 * "Call ended"). Only what still needs the user's attention sits above it: a hang-up that
 * wasn't confirmed, or why the call failed. Nothing more can be sent.
 */
@Composable
private fun EndedTranscript(model: ActiveCallViewModel, reason: EndReason, modifier: Modifier) {
    Column(modifier.fillMaxWidth().testTag("call.endedPanel"), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        when (reason) {
            EndReason.HangUpUnconfirmed -> IconLabel(
                "Couldn't confirm the hang-up. Check the call is over.",
                Icons.Filled.Warning,
                Modifier.fillMaxWidth().testTag("call.endedWarning"),
                color = IsharaColors.Orange,
                style = IsharaType.subheadline.copy(fontWeight = FontWeight.SemiBold),
            )
            is EndReason.Failed -> WarningLabel(
                reason.message,
                Modifier.fillMaxWidth().testTag("call.endedWarning"),
                style = IsharaType.subheadline.copy(fontWeight = FontWeight.SemiBold),
            )
            EndReason.UserEnded, EndReason.RemoteEnded -> Unit
        }
        CaptionHistory(model.captions, Modifier.fillMaxWidth().weight(1f), isCallOver = true)
        Spacer(Modifier.height(4.dp))
    }
}

/**
 * Screen 3 body beside the video, top to bottom in the order the eyes move: what the camera
 * needs, chips. The draft, quick replies and SEND live in the action bar. On a delegated call
 * (D9) there are no chips: the camera is there only to answer the agent (attended); an
 * unattended call has none.
 */
@Composable
private fun SigningPanel(model: ActiveCallViewModel, chipsInView: BringIntoViewRequester, bannerInView: BringIntoViewRequester) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (model.watchesSigns) {
            CantSeeYouNotice(model.cameraState)
            ReplayMenu(model.recognition.replayOptions, model.recognition::replay)
        }
        model.errorMessage?.let { CallErrorBanner(it) }
        if (model.showsFramingHint) FramingHint()
        model.candidate?.let { CandidateTile(it, model::acceptCandidate, model::dismissCandidate) }
        if (model.isDelegated) {
            DelegatedCallNote(model.isAttended)
        } else {
            if (model.showsDeliveryResult) DeliveryBanner(model.delivery, Modifier.bringIntoViewRequester(bannerInView))
            ChipRow(model.chips, model::removeChip, Modifier.bringIntoViewRequester(chipsInView))
        }
    }
}

/** Screen 4 body beside the video: the camera keeps watching so the user can sign the next thing. */
@Composable
private fun SpeakingPanel(model: ActiveCallViewModel) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        CantSeeYouNotice(model.cameraState)
        if (model.isStopTooLate) StopTooLateBanner()
        model.errorMessage?.let { CallErrorBanner(it) }
    }
}

/** What the user is (and isn't) expected to do while the agent makes the call for them. */
@Composable
private fun DelegatedCallNote(attended: Boolean) {
    IconLabel(
        if (attended) {
            "The agent is making the call for you. When a decision is yours it will ask here: sign or tap one of the answers shown."
        } else {
            "The agent is making the call for you. You can put the phone down; the notes will be here when it ends."
        },
        if (attended) Icons.Filled.Person else Icons.Filled.Call,
        modifier = Modifier.fillMaxWidth().semantics(mergeDescendants = true) {}.testTag("call.delegatedNote"),
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        style = IsharaType.subheadline,
    )
}

/**
 * D9: no draft, quick replies or SEND; the agent speaks from the approved brief. The user
 * answers its questions (attended) and reads the notes afterwards.
 */
@Composable
private fun DelegatedBar(
    model: ActiveCallViewModel,
    stage: ActiveCallStage,
    layout: CallLayout,
    onLeave: () -> Unit,
    onShowNotes: (() -> Unit)?,
) {
    val isOver = stage is ActiveCallStage.Ended || (stage is ActiveCallStage.ConnectionLost && !stage.isReconnecting)
    if (isOver) {
        // The notes are what the user came back for, so they lead.
        if (onShowNotes != null) {
            PrimaryButton("Call summary", onShowNotes, Modifier.testTag("call.notes"), icon = Icons.Filled.Info, fillWidth = true)
        }
        BackHomeButton(onLeave, Modifier.fillMaxWidth())
    } else {
        // Leaves room for the answer buttons and the status bar with End above.
        model.openQuestion?.let { question ->
            AskCard(question, model::answer, detailsMaxHeight = layout.sentenceMaxHeight * 0.5f)
        }
    }
}

/**
 * Draft + quick replies + Clear + SEND while signing, the spoken sentence + STOP while
 * speaking, Back to Home once ended.
 */
@Composable
private fun LiveBar(model: ActiveCallViewModel, stage: ActiveCallStage, sentenceMaxHeight: Dp, onLeave: () -> Unit) {
    when (stage) {
        is ActiveCallStage.Ended -> BackHomeButton(onLeave, Modifier.fillMaxWidth())
        is ActiveCallStage.Speaking -> {
            PinnedSentence(sentenceMaxHeight) {
                // Once STOP is refused it is still being spoken, not stopping.
                SpeakingCard(stage.text, isStopRequested = model.isStopRequested && !model.isStopTooLate)
            }
            DestructiveButton(
                "Stop",
                model::stop,
                Modifier.testTag("call.stop"),
                enabled = !model.isStopRequested,
                icon = StopIcon,
            )
        }
        ActiveCallStage.Signing -> {
            model.openQuestion?.let { AskCard(it, model::answer) }
            QuickReplyBar(model::choose, enabled = model.canUseQuickReplies)
            PinnedSentence(sentenceMaxHeight) { DraftCard(model.draft, isComposing = model.isComposing) }
            SendRow(model)
        }
        // Pending drafts are wiped when the connection drops, so there is no sentence to show;
        // the disabled controls keep the layout steady.
        is ActiveCallStage.ConnectionLost -> {
            QuickReplyBar(model::choose, enabled = model.canUseQuickReplies)
            SendRow(model)
        }
    }
}

@Composable
private fun SendRow(model: ActiveCallViewModel) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
        // Sized to its label so the word never wraps at large text sizes; SEND takes the rest.
        IsharaTextButton(
            "Clear",
            model::clear,
            Modifier.testTag("call.clear"),
            enabled = model.chips.isNotEmpty() || model.draft != null,
        )
        PrimaryButton(
            "Send",
            model::send,
            Modifier.weight(1f).testTag("call.send").semantics { contentDescription = "Send reply" },
            enabled = model.canSend,
            icon = Icons.AutoMirrored.Filled.Send,
        )
    }
}

@Composable
private fun BackHomeButton(onLeave: () -> Unit, modifier: Modifier) {
    TonalButton("Back to Home", onLeave, modifier.testTag("call.backHome"), icon = Icons.Filled.Home)
}

/** The exact sentence being spoken. */
@Composable
private fun SpeakingCard(text: String, isStopRequested: Boolean) {
    val title = if (isStopRequested) "Stopping…" else "Speaking now…"
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(IsharaColors.Purple.copy(alpha = 0.2f), RoundedCornerShape(16.dp))
            .semantics(mergeDescendants = true) { contentDescription = "${title.removeSuffix("…")}: $text" }
            .testTag("call.speaking")
            .padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text(title, style = IsharaType.subheadline.copy(fontWeight = FontWeight.SemiBold))
        Text("\u201C$text\u201D", style = IsharaType.title3.copy(fontWeight = FontWeight.SemiBold))
    }
}

/** SF Symbols `stop.fill`: a rounded square. */
private val StopIcon: ImageVector = ImageVector.Builder("Stop", 24.dp, 24.dp, 24f, 24f).apply {
    path(fill = SolidColor(Color.Black)) {
        moveTo(7f, 5f)
        lineTo(17f, 5f)
        quadTo(19f, 5f, 19f, 7f)
        lineTo(19f, 17f)
        quadTo(19f, 19f, 17f, 19f)
        lineTo(7f, 19f)
        quadTo(5f, 19f, 5f, 17f)
        lineTo(5f, 7f)
        quadTo(5f, 5f, 7f, 5f)
        close()
    }
}.build()
