package ai.ishara.demo.ui.classic

import ai.ishara.demo.recognition.GetReadyModel
import ai.ishara.demo.recognition.RecognitionController
import ai.ishara.demo.ui.components.BigActionButton
import ai.ishara.demo.ui.components.CallingNumberNote
import ai.ishara.demo.ui.components.CameraCard
import ai.ishara.demo.ui.theme.IsharaColors
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

/**
 * Get ready: the framing checklist and the 2 s hands-at-rest calibration; Start stays off
 * until both are done. The app root starts [recognition]. Placeholder layout; the next phase
 * ports iOS `GetReadyView` here, keeping these parameters.
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
    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        TextButton(onClick = onBack) { Text("Back") }
        Text("Get ready", style = MaterialTheme.typography.headlineMedium)
        CameraCard(camera = recognition.camera, state = null)
        failure?.let { Text(it, color = IsharaColors.Red) }
        notice?.let { Text(it, color = IsharaColors.Orange) }
        GetReadyModel.Check.entries.forEach { check ->
            Text("${if (check in state.passedChecks) "✓" else "○"} ${check.title}", modifier = Modifier.testTag("getReady.check.${check.name.lowercase()}"))
        }
        Text("Rest your hands for 2 seconds")
        LinearProgressIndicator(progress = { state.calibrationProgress.toFloat() }, modifier = Modifier.fillMaxWidth())
        CallingNumberNote()
        if (modeDescription.isNotEmpty()) Text(modeDescription, style = MaterialTheme.typography.bodySmall)
        BigActionButton(startTitle, MaterialTheme.colorScheme.primary, onStart, Modifier.testTag("getReady.start"), enabled = state.isReady)
    }
}
