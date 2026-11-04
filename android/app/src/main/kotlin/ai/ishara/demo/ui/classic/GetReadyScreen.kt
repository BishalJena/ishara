package ai.ishara.demo.ui.classic

import ai.ishara.demo.recognition.GetReadyModel
import ai.ishara.demo.recognition.RecognitionController
import ai.ishara.demo.ui.components.BottomBar
import ai.ishara.demo.ui.components.CallingNumberNote
import ai.ishara.demo.ui.components.CameraCard
import ai.ishara.demo.ui.components.InfoLabel
import ai.ishara.demo.ui.components.LargeTitle
import ai.ishara.demo.ui.components.PrimaryButton
import ai.ishara.demo.ui.components.ReplayMenu
import ai.ishara.demo.ui.components.TopBar
import ai.ishara.demo.ui.components.WarningLabel
import ai.ishara.demo.ui.theme.IsharaColors
import ai.ishara.demo.ui.theme.IsharaType
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Phone
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.unit.dp
import java.util.Locale
import kotlin.math.max

/**
 * Screen 2 (iOS `GetReadyView`): the framing checklist and the 2 s hands-at-rest calibration,
 * then Start; Start stays off until both are done. Recognition drives both, from real frames or
 * on timers when it replays fixed results; the app root starts [recognition]. The camera card
 * asks for the camera permission when a live camera is watched.
 */
@Composable
fun GetReadyScreen(
    recognition: RecognitionController,
    modeDescription: String,
    startTitle: String,
    onStart: () -> Unit,
    onBack: () -> Unit,
) {
    val state by recognition.getReady.state.collectAsState()
    val failure by recognition.failure.collectAsState()
    val notice by recognition.notice.collectAsState()
    Column(Modifier.fillMaxSize()) {
        TopBar(leading = { TextButton(onClick = onBack, modifier = Modifier.testTag("getReady.back")) { Text("Back", style = IsharaType.body) } })
        Column(
            modifier = Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(bottom = 16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            LargeTitle("Get ready")
            Column(Modifier.padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                Text("Prop the phone about an arm away.", style = IsharaType.title3)
                Box {
                    CameraCard(camera = recognition.camera)
                    ReplayMenu(recognition.replayOptions, recognition::replay, Modifier.align(Alignment.BottomEnd).padding(10.dp), tint = Color.White)
                }
                val shownFailure = failure
                val shownNotice = notice
                if (shownFailure != null) {
                    WarningLabel(shownFailure, Modifier.testTag("getReady.failure"))
                } else if (shownNotice != null) {
                    InfoLabel(shownNotice, Modifier.testTag("getReady.notice"))
                }
                ChecklistCard(state.passedChecks)
                CalibrationCard(state.calibrationProgress, isActive = state.allChecksPassed)
            }
        }
        BottomBar {
            if (modeDescription.isNotEmpty()) {
                Text(modeDescription, style = IsharaType.footnote, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            // Repeated from Home: this is where the call is actually placed.
            CallingNumberNote()
            PrimaryButton(
                startTitle,
                onStart,
                Modifier.testTag("getReady.start"),
                enabled = state.isReady,
                icon = Icons.Filled.Phone,
                fillWidth = true,
            )
        }
    }
}

@Composable
private fun ChecklistCard(passed: Set<GetReadyModel.Check>) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(IsharaColors.Green.copy(alpha = 0.15f), RoundedCornerShape(16.dp))
            .padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        GetReadyModel.Check.entries.forEach { check ->
            val isPassed = check in passed
            Row(
                modifier = Modifier
                    .testTag("getReady.check.${check.name.lowercase()}")
                    .clearAndSetSemantics {
                        contentDescription = "${check.title}: ${if (isPassed) "yes" else "checking"}"
                        stateDescription = if (isPassed) "passed" else "checking"
                    },
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                if (isPassed) {
                    Icon(Icons.Filled.CheckCircle, contentDescription = null, tint = IsharaColors.Green, modifier = Modifier.size(20.dp))
                } else {
                    DottedCircle()
                }
                Text(check.title, style = IsharaType.callout)
            }
        }
    }
}

/** iOS `circle.dotted`: a check still running. */
@Composable
private fun DottedCircle() {
    val color = MaterialTheme.colorScheme.onSurfaceVariant
    Box(
        Modifier.size(20.dp).padding(2.dp).drawBehind {
            drawCircle(
                color,
                style = Stroke(width = 2.dp.toPx(), pathEffect = PathEffect.dashPathEffect(floatArrayOf(2.dp.toPx(), 3.dp.toPx()))),
            )
        },
    )
}

@Composable
private fun CalibrationCard(progress: Double, isActive: Boolean) {
    val remaining = when {
        !isActive -> "Starts once the checklist is done."
        progress >= 1 -> "Done"
        else -> String.format(Locale.US, "%.1f s left", max(0.0, GetReadyModel.CALIBRATION_SECONDS * (1 - progress)))
    }
    val title = if (progress >= 1) "Hands at rest: calibrated" else "Rest your hands on the table…"
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(IsharaColors.Yellow.copy(alpha = 0.2f), RoundedCornerShape(16.dp))
            .semantics(mergeDescendants = true) {}
            .testTag("getReady.calibration")
            .padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text(title, style = IsharaType.headline)
        LinearProgressIndicator(
            progress = { progress.toFloat() },
            color = IsharaColors.Orange,
            trackColor = IsharaColors.Gray.copy(alpha = 0.25f),
            strokeCap = androidx.compose.ui.graphics.StrokeCap.Round,
            gapSize = 0.dp,
            drawStopIndicator = {},
            modifier = Modifier.fillMaxWidth().height(4.dp),
        )
        Text(remaining, style = IsharaType.subheadline, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
