package ai.ishara.demo.ui.classic

import ai.ishara.demo.call.ActiveCallStage
import ai.ishara.demo.call.ActiveCallViewModel
import ai.ishara.demo.call.ActiveCallViewModel.Delivery
import ai.ishara.demo.ui.components.AskCard
import ai.ishara.demo.ui.components.BigActionButton
import ai.ishara.demo.ui.components.BottomBar
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
import ai.ishara.demo.ui.components.IconLabel
import ai.ishara.demo.ui.components.PinnedSentence
import ai.ishara.demo.ui.components.QuickReplyBar
import ai.ishara.demo.ui.components.ReplayMenu
import ai.ishara.demo.ui.components.StopTooLateBanner
import ai.ishara.demo.ui.components.isAccessibilityTextSize
import ai.ishara.demo.ui.theme.IsharaColors
import ai.ishara.demo.ui.theme.IsharaType
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.relocation.BringIntoViewRequester
import androidx.compose.foundation.relocation.bringIntoViewRequester
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.Call
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Person
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
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
import androidx.compose.ui.unit.max
import androidx.compose.ui.unit.min

/**
 * Screens 3 and 4 (iOS `ActiveCallView`): signing a reply, then speaking it; also the lost
 * connection and the ended call. The app root runs [model] while this is shown. [onShowNotes]
 * is set for a delegated (D9) call.
 *
 * The sentence SEND or STOP acts on lives in the pinned action bar right above its button, so
 * it can never scroll away or hide behind it at any text size; the captions give up height at
 * large text sizes (and, while the agent asks, for the camera) so the chips stay reachable.
 */
@Composable
fun ActiveCallScreen(model: ActiveCallViewModel, onLeave: () -> Unit, onShowNotes: (() -> Unit)?) {
    val stage = ActiveCallStage.of(model)
    val density = LocalDensity.current
    val isAccessibilitySize = isAccessibilityTextSize()
    // Heights of the status bar and the action bar. Neither depends on the caption box, so
    // sizing the captions from them (and the screen) can't feed back into a layout loop.
    var statusBarHeight by remember { mutableStateOf<Dp?>(null) }
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
        val screenHeight = maxHeight
        val layout = CallLayout(
            screenHeight = screenHeight,
            statusBarHeight = statusBarHeight,
            actionBarHeight = actionBarHeight,
            scaledCaptionHeight = CallLayout.CAPTION_HEIGHT * density.fontScale,
            keepsCameraInView = model.isDelegated && model.watchesSigns && model.openQuestion != null && !isAccessibilitySize,
        )
        Column(Modifier.fillMaxSize()) {
            Column(
                modifier = Modifier.weight(1f).padding(start = 16.dp, end = 16.dp, top = CallLayout.TOP_PADDING),
                verticalArrangement = Arrangement.spacedBy(CallLayout.SPACING),
            ) {
                CallStatusBar(
                    model.setup.contact.name,
                    model.phase,
                    model.isSpeaking,
                    model.connectedAt,
                    onEnd = model::end,
                    modifier = Modifier.onSizeChanged { statusBarHeight = with(density) { it.height.toDp() } },
                )
                CaptionHistory(model.captions, Modifier.fillMaxWidth().height(layout.captionBoxHeight), isCallOver = model.isCallOver)
                Column(Modifier.weight(1f).fillMaxWidth().verticalScroll(panelScroll)) {
                    when (stage) {
                        is ActiveCallStage.Ended -> CallEndedPanel(stage.reason)
                        is ActiveCallStage.ConnectionLost -> ConnectionLostPanel(stage.notice, stage.isReconnecting)
                        is ActiveCallStage.Speaking -> SpeakingPanel(model)
                        ActiveCallStage.Signing -> SigningPanel(model, chipsInView, bannerInView)
                    }
                    Spacer(Modifier.height(8.dp))
                }
            }
            BottomBar(
                Modifier
                    .onSizeChanged { actionBarHeight = with(density) { it.height.toDp() } }
                    .testTag("call.actionBar"),
                spacing = 12.dp,
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
 * The call screen's sizes, ported from iOS `ActiveCallView` (points become dp): the caption
 * box, the tallest the agent's question card may be, and the room for the pinned sentence.
 */
private class CallLayout(
    private val screenHeight: Dp,
    private val statusBarHeight: Dp?,
    private val actionBarHeight: Dp?,
    /** iOS `@ScaledMetric(relativeTo: .body) captionHeight = 150`: grows with the text size. */
    private val scaledCaptionHeight: Dp,
    /** The user signs the answer to the agent's question, so the camera stays in view above its card. */
    private val keepsCameraInView: Boolean,
) {
    /** Room for the pinned sentence; past this it scrolls inside its card. */
    val sentenceMaxHeight: Dp get() = screenHeight * 0.55f

    /**
     * At large text sizes the action bar takes much of the screen; the captions then give up
     * space so the chips stay reachable. While the agent asks they also give up what the
     * camera needs.
     */
    val captionBoxHeight: Dp
        get() {
            val preferred = min(scaledCaptionHeight, 240.dp)
            val bar = actionBarHeight ?: return preferred
            var height = min(preferred, (screenHeight - bar) * 0.4f)
            val status = statusBarHeight
            if (keepsCameraInView && status != null) {
                height = min(height, screenHeight - bar - chromeHeight(status) - CAMERA_ROOM)
            }
            return max(MIN_CAPTION_HEIGHT, height)
        }

    /** The tallest the question card may be with the captions at their smallest and the camera's room left. */
    val askCardMaxHeight: Dp?
        get() {
            val status = statusBarHeight
            if (!keepsCameraInView || status == null) return null
            return screenHeight - chromeHeight(status) - MIN_CAPTION_HEIGHT - CAMERA_ROOM - ACTION_BAR_PADDING * 2
        }

    /** Everything above the scrolling panel but the captions: top padding, status bar, the two gaps. */
    private fun chromeHeight(statusBar: Dp): Dp = TOP_PADDING + statusBar + SPACING * 2

    companion object {
        val CAPTION_HEIGHT = 150.dp
        val MIN_CAPTION_HEIGHT = 80.dp

        /** The whole live camera card (a 170 dp preview in 10 dp of padding) and a little space under it. */
        val CAMERA_ROOM = 190.dp + 8.dp
        val TOP_PADDING = 8.dp
        val SPACING = 12.dp
        val ACTION_BAR_PADDING = 16.dp
    }
}

private fun showsDeliveryBanner(model: ActiveCallViewModel): Boolean {
    if (model.isDelegated || !model.showsDeliveryResult) return false
    return when (model.delivery) {
        Delivery.Delivered, Delivery.DeliveredDespiteStop, is Delivery.NotDelivered, is Delivery.Stopped -> true
        Delivery.Idle, is Delivery.Speaking -> false
    }
}

/**
 * Screen 3 body, top to bottom in the order the eyes move: camera, chips. The draft, quick
 * replies and SEND live in the action bar. On a delegated call (D9) there are no chips: the
 * camera is there only to answer the agent (attended); an unattended call shows no camera.
 */
@Composable
private fun SigningPanel(model: ActiveCallViewModel, chipsInView: BringIntoViewRequester, bannerInView: BringIntoViewRequester) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (model.watchesSigns) {
            Box(Modifier.testTag("call.camera")) {
                CameraCard(camera = model.recognition.camera, state = model.cameraState)
                ReplayMenu(
                    model.recognition.replayOptions,
                    model.recognition::replay,
                    Modifier.align(androidx.compose.ui.Alignment.BottomEnd).padding(10.dp),
                )
            }
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

/** Screen 4 body: the camera keeps watching so the user can sign the next thing. */
@Composable
private fun SpeakingPanel(model: ActiveCallViewModel) {
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        CameraCard(camera = model.recognition.camera, state = model.cameraState)
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
        if (onShowNotes != null) {
            BigActionButton("See the call notes", IsharaColors.Blue, onShowNotes, Modifier.testTag("call.notes"), icon = Icons.Filled.Info)
        }
        BackHomeButton(onLeave, tint = IsharaColors.Gray.copy(alpha = 0.3f), foreground = MaterialTheme.colorScheme.onSurface)
    } else {
        // Leaves room for the answer buttons and the status bar with End above, and at standard
        // text sizes for the camera too.
        model.openQuestion?.let { question ->
            AskCard(question, model::answer, detailsMaxHeight = layout.sentenceMaxHeight * 0.5f, maxHeight = layout.askCardMaxHeight)
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
        is ActiveCallStage.Ended -> BackHomeButton(onLeave, tint = IsharaColors.Blue, foreground = Color.White)
        is ActiveCallStage.Speaking -> {
            PinnedSentence(sentenceMaxHeight) {
                // Once STOP is refused it is still being spoken, not stopping.
                SpeakingCard(stage.text, isStopRequested = model.isStopRequested && !model.isStopTooLate)
            }
            BigActionButton(
                "STOP",
                IsharaColors.Red,
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
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        // Sized to its label so the word never wraps at large text sizes; SEND takes the rest.
        BigActionButton(
            "Clear",
            IsharaColors.Gray.copy(alpha = 0.3f),
            model::clear,
            Modifier.testTag("call.clear"),
            enabled = model.chips.isNotEmpty() || model.draft != null,
            foreground = MaterialTheme.colorScheme.onSurface,
            fillWidth = false,
        )
        BigActionButton(
            "SEND",
            IsharaColors.Orange,
            model::send,
            Modifier.weight(1f).testTag("call.send").semantics { contentDescription = "Send reply" },
            enabled = model.canSend,
            icon = Icons.AutoMirrored.Filled.Send,
        )
    }
}

@Composable
private fun BackHomeButton(onLeave: () -> Unit, tint: Color, foreground: Color) {
    BigActionButton("Back to Home", tint, onLeave, Modifier.testTag("call.backHome"), foreground = foreground)
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
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(title, style = IsharaType.headline)
        Text("\u201C$text\u201D", style = IsharaType.title2.copy(fontWeight = FontWeight.SemiBold))
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
