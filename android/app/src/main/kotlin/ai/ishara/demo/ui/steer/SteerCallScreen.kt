package ai.ishara.demo.ui.steer

import ai.ishara.demo.call.ActiveCallViewModel
import ai.ishara.demo.call.ActiveCallViewModel.Phase
import ai.ishara.demo.core.call.Caption
import ai.ishara.demo.core.call.ProposalOrigin
import ai.ishara.demo.recognition.CameraPermission
import ai.ishara.demo.ui.components.CallErrorBanner
import ai.ishara.demo.ui.components.CandidateTile
import ai.ishara.demo.ui.components.ChipRow
import ai.ishara.demo.ui.components.InitialsAvatar
import ai.ishara.demo.ui.components.PrimaryButton
import ai.ishara.demo.ui.components.epochSeconds
import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ListAlt
import androidx.compose.material.icons.filled.ArrowUpward
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.BackHand
import androidx.compose.material.icons.filled.Bookmark
import androidx.compose.material.icons.filled.CallEnd
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Keyboard
import androidx.compose.material.icons.filled.RecordVoiceOver
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedIconButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.delay

/**
 * The one call screen for steer calls (port of iOS `SteerCallView`): Ishara runs the call from
 * the typed request; the user watches the captions and steps in by typing (first) or signing.
 * Each agent line sits in the filling Send bar for its window; doing nothing lets it be spoken.
 * The app root runs [model].
 */
@Composable
fun SteerCallScreen(model: ActiveCallViewModel, onLeave: () -> Unit, onShowNotes: () -> Unit) {
    val colors = steerColors()
    var typed by rememberSaveable { mutableStateOf("") }
    /** What the user last sent, shown under its polished preview. */
    var lastTyped by rememberSaveable { mutableStateOf("") }
    var isSigning by rememberSaveable { mutableStateOf(false) }
    /** Lines sent from signs, so each "You" line keeps the icon of how it was made. */
    var signedLines by remember { mutableStateOf(emptySet<String>()) }
    var typing by remember { mutableStateOf(false) }
    val fieldFocus = remember { FocusRequester() }
    val focusManager = LocalFocusManager.current
    val notThrough = SteerCallText.notThrough(model)

    ReportPresence(model)
    OngoingCallEffect(model)
    // A call that got through goes straight on to its gist after a beat, so the last line can
    // be read; a call that didn't stays here with its tray of next steps.
    LaunchedEffect(model.isCallOver) {
        if (!model.isCallOver) return@LaunchedEffect
        focusManager.clearFocus()
        if (SteerCallText.notThrough(model) == null) {
            delay(2_000)
            onShowNotes()
        }
    }

    fun sendTyped() {
        val text = typed.trim()
        if (text.isEmpty()) return
        lastTyped = text
        model.say(text)
        typed = ""
        focusManager.clearFocus()
    }

    Column(Modifier.fillMaxSize().background(colors.background)) {
        Header(model, onShowNotes)
        StatusPill(
            text = SteerCallText.status(model, isSigning),
            icon = when {
                model.isCallOver -> Icons.Filled.CheckCircle
                model.isSteppingIn -> if (isSigning) Icons.Filled.BackHand else Icons.Filled.Keyboard
                else -> Icons.Filled.AutoAwesome
            },
            color = when {
                model.isCallOver -> colors.green
                model.phase == Phase.Live -> if (model.isSteppingIn) colors.blue else colors.purple
                else -> colors.secondary
            },
            modifier = Modifier.padding(horizontal = 20.dp).testTag("steer.status"),
        )
        FactsStrip(CallFacts.extract(model.captions.filter { it.speaker == Caption.Speaker.RECEPTIONIST }.map { it.text }))
        Captions(model, signedLines, Modifier.weight(1f))
        model.errorMessage?.let { CallErrorBanner(it, Modifier.padding(horizontal = 12.dp)) }
        if (notThrough != null) {
            NotThroughTray(notThrough, onCallAgain = onLeave, onShowNotes = onShowNotes)
        } else {
            Column(
                verticalArrangement = Arrangement.spacedBy(10.dp),
                modifier = Modifier
                    .fillMaxWidth()
                    .background(colors.bar)
                    .padding(start = 12.dp, end = 12.dp, top = 6.dp, bottom = 10.dp),
            ) {
                val cover = model.captions.lastOrNull { it.speaker == Caption.Speaker.AGENT }
                if (model.isSteppingIn && !isSigning && cover != null) CoverLine(cover.text, cover.at)
                model.proposal?.let { proposal ->
                    ProposalBar(
                        proposal = proposal,
                        onSendNow = model::approveProposal,
                        onEdit = {
                            // Either way the line drops into the field, ready to change.
                            typed = proposal.text
                            if (proposal.origin == ProposalOrigin.USER) model.editPreview() else model.beginSteppingIn()
                            isSigning = false
                            fieldFocus.requestFocus()
                        },
                    )
                    if (proposal.origin == ProposalOrigin.USER && lastTyped.isNotEmpty()) {
                        Text(
                            "You typed: \u201C$lastTyped\u201D",
                            style = SteerType.caption2,
                            color = colors.secondary,
                            modifier = Modifier.testTag("steer.youTyped"),
                        )
                    }
                }
                if (isSigning) {
                    SigningPanel(
                        model = model,
                        onType = {
                            isSigning = false
                            model.clear()
                            if (typed.isEmpty()) model.cancelSteppingIn()
                        },
                        onSend = {
                            model.draft?.let { signedLines = signedLines + it.text }
                            model.send()
                        },
                    )
                } else if (!model.isCallOver) {
                    // Under Ishara's proposed line too (design G2): tapping one replaces it.
                    if (model.proposal?.origin != ProposalOrigin.USER && !typing && model.phase == Phase.Live) {
                        QuickReplies(model.captions.lastOrNull { it.speaker == Caption.Speaker.RECEPTIONIST }?.text) { reply ->
                            model.beginSteppingIn()
                            lastTyped = reply
                            model.say(reply)
                        }
                    }
                    TypingBar(
                        typed = typed,
                        onTypedChange = { typed = it },
                        isCallOver = model.isCallOver,
                        fieldFocus = fieldFocus,
                        onFocusChange = { focused ->
                            if (focused == typing) return@TypingBar
                            typing = focused
                            if (focused) model.beginSteppingIn() else if (typed.isEmpty()) model.cancelSteppingIn()
                        },
                        onSign = {
                            isSigning = true
                            focusManager.clearFocus()
                            model.beginSteppingIn()
                        },
                        onSend = ::sendTyped,
                    )
                }
                if (!model.isCallOver && !isSigning && !typing) {
                    Text(
                        "If you don't step in, Ishara keeps going. Nothing you type is spoken until you send it.",
                        style = SteerType.caption2,
                        color = colors.secondary,
                        textAlign = TextAlign.Center,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }
        }
    }
}

@Composable
private fun Header(model: ActiveCallViewModel, onShowNotes: () -> Unit) {
    val colors = steerColors()
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        modifier = Modifier.padding(horizontal = 20.dp, vertical = 8.dp),
    ) {
        InitialsAvatar(model.setup.contact.name, color = colors.blue)
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(
                model.setup.contact.name,
                style = SteerType.title3,
                fontWeight = FontWeight.Bold,
                color = colors.primary,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                SteerCallText.timer(model.connectedAt, model.phase, secondsClock()),
                style = SteerType.footnote,
                color = colors.secondary,
                modifier = Modifier.testTag("steer.timer"),
            )
        }
        if (model.isCallOver) {
            CapsuleButton("Gist", Icons.AutoMirrored.Filled.ListAlt, MaterialTheme.colorScheme.primary, MaterialTheme.colorScheme.onPrimary, "steer.gist", onShowNotes)
        } else {
            CapsuleButton("End", Icons.Filled.CallEnd, colors.red, Color.White, "steer.end", model::end)
        }
    }
}

@Composable
private fun Captions(model: ActiveCallViewModel, signedLines: Set<String>, modifier: Modifier) {
    val colors = steerColors()
    val scroll = rememberScrollState()
    val count = model.captions.size
    LaunchedEffect(count, model.followUps.size) { scroll.animateScrollTo(scroll.maxValue) }
    // Not lazy, like iOS: a call has a few dozen lines, and the list scrolls to its end on each one.
    Column(
        verticalArrangement = Arrangement.spacedBy(16.dp),
        modifier = modifier.fillMaxWidth().verticalScroll(scroll).padding(20.dp),
    ) {
        CoverLines.rows(model.captions).forEach { row ->
            val caption = row.caption
            val isLatest = row.index == count - 1
            val tag = when (caption.speaker) {
                Caption.Speaker.RECEPTIONIST -> "caption.receptionist"
                Caption.Speaker.AGENT -> "caption.agent"
                Caption.Speaker.USER -> "caption.you"
            }
            Column(
                verticalArrangement = Arrangement.spacedBy(4.dp),
                modifier = Modifier.fillMaxWidth().testTag(tag).semantics(mergeDescendants = true) {},
            ) {
                val speakerColor = when (caption.speaker) {
                    Caption.Speaker.RECEPTIONIST -> colors.secondary
                    Caption.Speaker.AGENT -> colors.purple
                    Caption.Speaker.USER -> colors.blue
                }
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    Icon(speakerIcon(caption, signedLines), contentDescription = null, tint = speakerColor, modifier = Modifier.size(13.dp))
                    Text(speakerName(caption.speaker, model), style = SteerType.caption, fontWeight = FontWeight.Bold, color = speakerColor)
                }
                Text(
                    caption.text,
                    style = if (isLatest && caption.speaker == Caption.Speaker.RECEPTIONIST) {
                        SteerType.title2.copy(fontWeight = FontWeight.SemiBold)
                    } else {
                        SteerType.body
                    },
                    color = if (isLatest) colors.primary else colors.secondary,
                )
                if (row.folded > 0) {
                    Text(
                        "Ishara covered the pause ${row.folded + 1} times while you replied",
                        style = SteerType.caption,
                        color = colors.tertiary,
                    )
                }
            }
        }
        model.followUps.lastOrNull()?.let { followUp ->
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier
                    .fillMaxWidth()
                    .background(colors.orange.copy(alpha = 0.12f), RoundedCornerShape(14.dp))
                    .padding(10.dp)
                    .testTag("steer.followUp")
                    .semantics(mergeDescendants = true) {},
            ) {
                Icon(Icons.Filled.Bookmark, contentDescription = null, tint = colors.orange, modifier = Modifier.size(16.dp))
                Text(
                    "They asked for something you didn't give. Saved as a follow-up: \u201C$followUp\u201D",
                    style = SteerType.footnote,
                    fontWeight = FontWeight.Medium,
                    color = colors.orange,
                )
            }
        }
    }
}

/** One-tap replies drawn from what the receptionist just asked; each goes out like a typed line. */
@Composable
private fun QuickReplies(lastLine: String?, onReply: (String) -> Unit) {
    val colors = steerColors()
    Row(
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        modifier = Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 4.dp).testTag("steer.quickReplies"),
    ) {
        QuickSteerReply.suggestions(lastLine).forEach { reply ->
            OutlinedButton(
                onClick = { onReply(reply) },
                border = null,
                colors = ButtonDefaults.outlinedButtonColors(
                    containerColor = MaterialTheme.colorScheme.primary.copy(alpha = 0.14f),
                    contentColor = MaterialTheme.colorScheme.primary,
                ),
                contentPadding = PaddingValues(horizontal = 12.dp, vertical = 4.dp),
                modifier = Modifier.testTag("steer.quickReply"),
            ) {
                Text(reply, style = SteerType.footnote, fontWeight = FontWeight.SemiBold, color = MaterialTheme.colorScheme.primary)
            }
        }
    }
}

@Composable
private fun TypingBar(
    typed: String,
    onTypedChange: (String) -> Unit,
    isCallOver: Boolean,
    fieldFocus: FocusRequester,
    onFocusChange: (Boolean) -> Unit,
    onSign: () -> Unit,
    onSend: () -> Unit,
) {
    val colors = steerColors()
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedIconButton(
            onClick = onSign,
            enabled = !isCallOver,
            border = null,
            modifier = Modifier
                .size(44.dp)
                .background(colors.tertiary.copy(alpha = 0.16f), CircleShape)
                .testTag("steer.sign"),
        ) {
            Icon(Icons.Filled.BackHand, contentDescription = "Sign instead", tint = MaterialTheme.colorScheme.primary)
        }
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier
                .weight(1f)
                .clip(RoundedCornerShape(24.dp))
                .background(colors.secondaryBackground)
                .padding(start = 14.dp, end = 6.dp, top = 6.dp, bottom = 6.dp),
        ) {
            PlainField(
                value = typed,
                onValueChange = onTypedChange,
                placeholder = "Type to step in…",
                style = SteerType.body,
                maxLines = 4,
                keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences, imeAction = ImeAction.Send),
                keyboardActions = KeyboardActions(onSend = { onSend() }),
                modifier = Modifier
                    .weight(1f)
                    .focusRequester(fieldFocus)
                    .onFocusChanged { onFocusChange(it.isFocused) }
                    .testTag("steer.field"),
            )
            FilledIconButton(
                onClick = onSend,
                enabled = typed.isNotBlank() && !isCallOver,
                colors = IconButtonDefaults.filledIconButtonColors(
                    containerColor = MaterialTheme.colorScheme.primary,
                    contentColor = MaterialTheme.colorScheme.onPrimary,
                    disabledContainerColor = colors.tertiary.copy(alpha = 0.18f),
                    disabledContentColor = colors.tertiary,
                ),
                modifier = Modifier.size(40.dp).testTag("steer.send"),
            ) {
                Icon(Icons.Filled.ArrowUpward, contentDescription = "Send", modifier = Modifier.size(20.dp))
            }
        }
    }
}

/**
 * Signing to step in: the camera, the signs so far, what Ishara will say, and Send. The camera
 * is asked for (and recognition started) when this panel first opens.
 */
@Composable
private fun SigningPanel(model: ActiveCallViewModel, onType: () -> Unit, onSend: () -> Unit) {
    val colors = steerColors()
    CameraWhileSigning(model)
    Column(verticalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.testTag("steer.signing")) {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.Top) {
            SteerCameraTile(
                camera = model.recognition.camera,
                state = model.cameraState,
                modifier = Modifier.size(width = 96.dp, height = 128.dp).clip(RoundedCornerShape(20.dp)),
            )
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Signs so far", style = SteerType.footnote, fontWeight = FontWeight.SemiBold, color = colors.secondary, modifier = Modifier.weight(1f))
                    TextButton(onClick = onType, contentPadding = PaddingValues(horizontal = 8.dp), modifier = Modifier.testTag("steer.type")) {
                        Icon(Icons.Filled.Keyboard, contentDescription = null, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.width(4.dp))
                        Text("Type", style = SteerType.footnote, fontWeight = FontWeight.SemiBold)
                    }
                }
                ChipRow(chips = model.chips, onRemove = model::removeChip)
                model.candidate?.let { CandidateTile(sign = it, onAccept = model::acceptCandidate, onDismiss = model::dismissCandidate) }
            }
        }
        model.draft?.let { draft ->
            Column(
                verticalArrangement = Arrangement.spacedBy(4.dp),
                modifier = Modifier
                    .fillMaxWidth()
                    .background(colors.secondaryBackground, RoundedCornerShape(16.dp))
                    .padding(12.dp)
                    .testTag("steer.signedDraft"),
            ) {
                Text("Ishara will say", style = SteerType.caption, fontWeight = FontWeight.SemiBold, color = colors.secondary)
                Text(draft.text, style = SteerType.body, fontWeight = FontWeight.Medium, color = colors.primary)
            }
        }
        PrimaryButton(
            "Send",
            onSend,
            Modifier.testTag("steer.sendSigned"),
            enabled = model.canSend,
            icon = Icons.Filled.ArrowUpward,
            fillWidth = true,
        )
    }
}

/**
 * Asks for the camera the first time the user signs and reports the answer to recognition
 * (Android asks only from an Activity); the answer is checked again on returning from Settings.
 * Recognition's frames start here: a steer call sets signing up only when the user signs.
 */
@Composable
private fun CameraWhileSigning(model: ActiveCallViewModel) {
    val context = LocalContext.current
    val camera = model.recognition.camera
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        camera?.onPermissionResult(granted)
    }
    fun granted() = ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED
    LaunchedEffect(model) {
        model.recognition.start()
        if (camera == null) return@LaunchedEffect
        if (granted()) camera.onPermissionResult(true) else if (camera.permission.value != CameraPermission.DENIED) launcher.launch(Manifest.permission.CAMERA)
    }
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    DisposableEffect(lifecycle, camera) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME && camera != null && camera.permission.value != CameraPermission.GRANTED && granted()) {
                camera.onPermissionResult(true)
            }
        }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer) }
    }
}

@Composable
private fun CapsuleButton(text: String, icon: ImageVector, container: Color, content: Color, tag: String, onClick: () -> Unit) {
    Button(
        onClick = onClick,
        colors = ButtonDefaults.buttonColors(containerColor = container, contentColor = content),
        contentPadding = PaddingValues(horizontal = 14.dp, vertical = 6.dp),
        modifier = Modifier.testTag(tag),
    ) {
        Icon(icon, contentDescription = null, modifier = Modifier.size(16.dp))
        Spacer(Modifier.width(6.dp))
        Text(text, style = SteerType.subheadline, fontWeight = FontWeight.SemiBold)
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

/** Epoch seconds, refreshed every quarter second for the call timer. */
@Composable
private fun secondsClock(): Double {
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

private fun speakerIcon(caption: Caption, signedLines: Set<String>): ImageVector = when (caption.speaker) {
    Caption.Speaker.RECEPTIONIST -> Icons.Filled.RecordVoiceOver
    Caption.Speaker.AGENT -> Icons.Filled.AutoAwesome
    Caption.Speaker.USER -> if (caption.text in signedLines) Icons.Filled.BackHand else Icons.Filled.Keyboard
}
