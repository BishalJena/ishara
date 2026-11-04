package ai.ishara.demo.ui.components

import ai.ishara.demo.call.ActiveCallViewModel.Phase
import ai.ishara.demo.core.call.CallState
import ai.ishara.demo.ui.theme.IsharaColors
import ai.ishara.demo.ui.theme.IsharaType
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import kotlin.math.max
import kotlinx.coroutines.delay

/** Contact, call state and elapsed time, with End always in reach. */
@Composable
fun CallStatusBar(
    contactName: String,
    phase: Phase,
    isSpeaking: Boolean,
    connectedAt: Double?,
    onEnd: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier
            .background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(16.dp))
            .padding(start = 14.dp, end = 8.dp, top = 8.dp, bottom = 8.dp)
            .heightIn(min = 48.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(modifier = Modifier.weight(1f).semantics(mergeDescendants = true) {}.testTag("call.status")) {
            Text(contactName, style = IsharaType.headline)
            Text(
                statusLine(phase, isSpeaking, connectedAt),
                style = IsharaType.subheadline,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        if (phase !is Phase.Ended) {
            Button(
                onClick = onEnd,
                colors = ButtonDefaults.buttonColors(containerColor = IsharaColors.Red, contentColor = androidx.compose.ui.graphics.Color.White),
                contentPadding = PaddingValues(horizontal = 20.dp, vertical = 8.dp),
                modifier = Modifier.heightIn(min = IsharaButtons.Height).testTag("call.end").semantics { contentDescription = "End call" },
            ) { Text("End", style = IsharaButtons.Label) }
        }
    }
}

@Composable
private fun statusLine(phase: Phase, isSpeaking: Boolean, connectedAt: Double?): String = when (phase) {
    is Phase.Connecting -> if (phase.state == CallState.RINGING) "Ringing…" else "Dialing…"
    is Phase.Interrupted -> "Connection lost · reconnecting…"
    is Phase.Disconnected -> "Connection lost"
    Phase.Live -> if (connectedAt == null) "In call" else "${if (isSpeaking) "Speaking" else "In call"} · ${elapsed(connectedAt)}"
    is Phase.Ended -> "Call ended"
}

/** "1:42" since [since] (epoch seconds), ticking every second. */
@Composable
fun elapsed(since: Double): String {
    val now by produceState(epochSeconds(), since) {
        while (true) {
            value = epochSeconds()
            delay(1_000)
        }
    }
    return formatElapsed(since, now)
}

fun formatElapsed(since: Double, now: Double): String {
    val seconds = max(0, (now - since).toInt())
    return "%d:%02d".format(seconds / 60, seconds % 60)
}

fun epochSeconds(): Double = System.currentTimeMillis() / 1000.0
