package ai.ishara.demo.ui.components

import ai.ishara.demo.call.ActiveCallViewModel
import ai.ishara.demo.call.ActiveCallViewModel.Delivery
import ai.ishara.demo.ui.theme.IsharaColors
import ai.ishara.demo.ui.theme.IsharaType
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.semantics
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
            .padding(horizontal = 12.dp, vertical = 8.dp)
            .semantics(mergeDescendants = true) {}
            .testTag(tag),
        verticalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        Text(title, style = IsharaType.headline)
        if (detail != null) Text(detail, style = IsharaType.subheadline)
    }
}

/** The socket dropped mid-call. Nothing is sent while it's down; the app reconnects. */
@Composable
fun ConnectionLostPanel(notice: String, isReconnecting: Boolean, modifier: Modifier = Modifier) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(16.dp))
            .padding(horizontal = 14.dp, vertical = 12.dp)
            .semantics(mergeDescendants = true) {}
            .testTag("call.connectionLostPanel"),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(Icons.Filled.Warning, contentDescription = null, tint = IsharaColors.Orange, modifier = Modifier.size(32.dp))
        Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(ActiveCallViewModel.CONNECTION_LOST_TITLE, style = IsharaType.headline)
            Text(
                if (isReconnecting) {
                    "$notice. Chips and draft were wiped. Reconnecting… You can still End the call."
                } else {
                    "$notice. Nothing will be sent. End the call to go back."
                },
                style = IsharaType.subheadline,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
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
