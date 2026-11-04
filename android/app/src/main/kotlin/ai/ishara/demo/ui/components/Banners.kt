package ai.ishara.demo.ui.components

import ai.ishara.demo.call.ActiveCallViewModel
import ai.ishara.demo.call.ActiveCallViewModel.Delivery
import ai.ishara.demo.call.ActiveCallViewModel.EndReason
import ai.ishara.demo.ui.theme.IsharaColors
import ai.ishara.demo.ui.theme.IsharaType
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Call
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Icon
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp

/** Result of the last SEND: delivered, not delivered with a manual retry, or stopped before it was spoken. */
@Composable
fun DeliveryBanner(delivery: Delivery, modifier: Modifier = Modifier) {
    when (delivery) {
        Delivery.Delivered -> StatusBanner(
            "✓ Delivered",
            "Chips and draft were wiped, so old text can't replay.",
            IsharaColors.Green,
            modifier,
        )
        // Never a plain "Delivered" after STOP: the user expected it not to be said.
        Delivery.DeliveredDespiteStop -> StatusBanner(
            "✓ Delivered — too late to stop",
            "It was already being spoken when you tapped STOP. Send a correction if you need to.",
            IsharaColors.Green,
            modifier,
        )
        // The sentence itself is not repeated: the draft card shows exactly what SEND will speak.
        is Delivery.NotDelivered -> StatusBanner(
            "Not delivered — tap SEND again",
            "Your last reply was not spoken. Nothing is resent unless you tap SEND.",
            IsharaColors.Orange,
            modifier,
        )
        // A deliberate STOP is not a failure: say so, without urging a resend.
        is Delivery.Stopped -> StatusBanner("Stopped. Nothing was spoken.", "Tap SEND to send it anyway, or Clear.", IsharaColors.Gray, modifier)
        Delivery.Idle, is Delivery.Speaking -> Unit
    }
}

/** STOP was refused because the reply is already being spoken. */
@Composable
fun StopTooLateBanner(modifier: Modifier = Modifier) {
    StatusBanner(
        "Too late to stop — it's already being spoken",
        "Send a correction once it's done.",
        IsharaColors.Orange,
        modifier,
        tag = "call.stopTooLateBanner",
    )
}

/** A backend error, in words. Errors never send anything. */
@Composable
fun CallErrorBanner(message: String, modifier: Modifier = Modifier) {
    StatusBanner(message, null, IsharaColors.Red, modifier, tag = "call.errorBanner")
}

@Composable
private fun StatusBanner(title: String, detail: String?, color: Color, modifier: Modifier, tag: String = "call.deliveryBanner") {
    val shape = RoundedCornerShape(14.dp)
    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(color.copy(alpha = 0.2f), shape)
            .border(1.5.dp, color, shape)
            .padding(horizontal = 16.dp, vertical = 10.dp)
            .semantics(mergeDescendants = true) {}
            .testTag(tag),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Text(title, style = IsharaType.headline)
        if (detail != null) Text(detail, style = IsharaType.subheadline)
    }
}

/** Shown after End, a hang-up or a lost connection. Nothing more is sent. */
@Composable
fun CallEndedPanel(reason: EndReason, modifier: Modifier = Modifier) {
    PanelCard(modifier.testTag("call.endedPanel")) {
        PanelIcon(if (reason is EndReason.Failed) Icons.Filled.Warning else Icons.Filled.Call)
        Text(
            when (reason) {
                EndReason.UserEnded, EndReason.HangUpUnconfirmed -> "You ended the call"
                EndReason.RemoteEnded -> "The call ended"
                is EndReason.Failed -> reason.message
            },
            style = IsharaType.title2.copy(fontWeight = FontWeight.Bold),
            textAlign = TextAlign.Center,
        )
        if (reason == EndReason.HangUpUnconfirmed) {
            IconLabel(
                "Couldn't confirm the hang-up. Check the call is over.",
                Icons.Filled.Warning,
                color = IsharaColors.Orange,
                style = IsharaType.headline,
            )
        }
        Text(
            "Nothing more will be sent. Any unsent draft was wiped.",
            style = IsharaType.body,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
        )
    }
}

/** The socket dropped mid-call. Nothing is sent while it's down; the app reconnects. */
@Composable
fun ConnectionLostPanel(notice: String, isReconnecting: Boolean, modifier: Modifier = Modifier) {
    PanelCard(modifier.testTag("call.connectionLostPanel")) {
        PanelIcon(Icons.Filled.Warning)
        Text(ActiveCallViewModel.CONNECTION_LOST_TITLE, style = IsharaType.title2.copy(fontWeight = FontWeight.Bold))
        Text(
            if (isReconnecting) {
                "$notice. Chips and draft were wiped. Reconnecting… You can still End the call."
            } else {
                "$notice. Nothing will be sent. End the call to go back."
            },
            style = IsharaType.body,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
        )
    }
}

@Composable
private fun PanelIcon(icon: ImageVector) {
    Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.size(48.dp))
}

@Composable
private fun PanelCard(modifier: Modifier, content: @Composable () -> Unit) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(16.dp))
            .padding(24.dp)
            .semantics(mergeDescendants = true) {},
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) { content() }
}

/**
 * Calls come from Ishara's calling number (Bolna's, Path B), never the user's own, and the
 * receptionist hears an automated voice. Shown on Home and again on Get ready.
 */
const val CALLING_NUMBER_NOTE = "Calls are placed from Ishara's calling number, not your own number. " +
    "The receptionist hears an automated voice reading what you approve."

@Composable
fun CallingNumberNote(modifier: Modifier = Modifier) {
    InfoLabel(
        CALLING_NUMBER_NOTE,
        modifier = modifier.fillMaxWidth().semantics(mergeDescendants = true) {}.testTag("callingNumberNote"),
        style = IsharaType.footnote,
    )
}
