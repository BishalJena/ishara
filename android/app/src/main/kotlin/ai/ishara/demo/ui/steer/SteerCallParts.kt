package ai.ishara.demo.ui.steer

import ai.ishara.demo.core.call.Proposal
import ai.ishara.demo.core.call.ProposalOrigin
import ai.ishara.demo.ui.components.epochSeconds
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ListAlt
import androidx.compose.material.icons.automirrored.filled.PhoneMissed
import androidx.compose.material.icons.automirrored.filled.Undo
import androidx.compose.material.icons.filled.ArrowUpward
import androidx.compose.material.icons.filled.CalendarToday
import androidx.compose.material.icons.filled.CurrencyRupee
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.GraphicEq
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButtonDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlin.math.roundToInt

/**
 * The filling Send bar (iOS `ProposalBar`): the proposed line fills from left to right over its
 * window and is spoken when full. Tap the arrow to send now, the line or the pencil to take it over.
 */
@Composable
fun ProposalBar(proposal: Proposal, onSendNow: () -> Unit, onEdit: () -> Unit) {
    val colors = steerColors()
    val tint = if (proposal.origin == ProposalOrigin.AGENT) colors.purple else colors.blue
    // The fill runs once over what is left of the window (a finite animation, so Compose tests
    // can still go idle); the countdown reads the clock four times a second.
    val fill = remember(proposal.turnId) { Animatable(proposal.progress(epochSeconds()).toFloat()) }
    LaunchedEffect(proposal.turnId) {
        val remaining = ((1 - fill.value) * proposal.windowS * 1000).roundToInt()
        fill.animateTo(1f, tween(durationMillis = remaining, easing = LinearEasing))
    }
    val now by produceState(epochSeconds(), proposal.turnId) {
        while (true) {
            value = epochSeconds()
            delay(250)
        }
    }
    val progress = fill.value
    val label = SteerCallText.proposalLabel(proposal, now)
    Box(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(22.dp))
            .background(tint.copy(alpha = 0.12f)),
    ) {
        Box(Modifier.matchParentSize()) {
            Box(Modifier.fillMaxHeight().fillMaxWidth(progress).background(tint.copy(alpha = 0.28f)).testTag("steer.proposalFill"))
        }
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
        ) {
            Column(
                verticalArrangement = Arrangement.spacedBy(3.dp),
                modifier = Modifier
                    .weight(1f)
                    .clickable(onClick = onEdit)
                    .testTag("steer.proposal")
                    .clearAndSetSemantics {
                        role = Role.Button
                        contentDescription = if (proposal.origin == ProposalOrigin.AGENT) {
                            "Ishara will say ${proposal.text}. Tap to edit."
                        } else {
                            "Saying ${proposal.text}. Tap to edit."
                        }
                        stateDescription = label
                    },
            ) {
                Text(label, style = SteerType.caption, fontWeight = FontWeight.SemiBold, color = tint, modifier = Modifier.testTag("steer.proposalLabel"))
                Text(proposal.text, style = SteerType.subheadline, fontWeight = FontWeight.SemiBold, color = colors.primary)
            }
            val isAgent = proposal.origin == ProposalOrigin.AGENT
            FilledIconButton(
                onClick = if (isAgent) onSendNow else onEdit,
                colors = IconButtonDefaults.filledIconButtonColors(containerColor = tint, contentColor = Color.White),
                modifier = Modifier.size(40.dp).testTag("steer.proposalAction"),
            ) {
                Icon(
                    if (isAgent) Icons.Filled.ArrowUpward else Icons.Filled.Edit,
                    contentDescription = if (isAgent) "Send now" else "Edit",
                )
            }
        }
    }
}

/**
 * While the user types: what Ishara just said to the receptionist to cover the pause, and how
 * long they've been waiting (iOS `CoverLine`). [since] in epoch seconds.
 */
@Composable
fun CoverLine(text: String, since: Double) {
    val colors = steerColors()
    val waited by produceState(seconds(since)) {
        while (true) {
            value = seconds(since)
            delay(1_000)
        }
    }
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        modifier = Modifier
            .fillMaxWidth()
            .background(colors.purple.copy(alpha = 0.08f), RoundedCornerShape(18.dp))
            .padding(horizontal = 14.dp, vertical = 10.dp)
            .testTag("steer.cover"),
    ) {
        Icon(Icons.Filled.GraphicEq, contentDescription = null, tint = colors.purple, modifier = Modifier.size(20.dp))
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(1.dp)) {
            Text("Ishara just said", style = SteerType.caption2, fontWeight = FontWeight.SemiBold, color = colors.purple)
            Text("\u201C$text\u201D", style = SteerType.footnote, fontWeight = FontWeight.SemiBold, color = colors.primary)
        }
        Text(
            "$waited s",
            style = SteerType.caption,
            fontWeight = FontWeight.Bold,
            color = colors.secondary,
            modifier = Modifier.semantics { contentDescription = "waiting $waited seconds" },
        )
    }
}

private fun seconds(since: Double): Int = maxOf(0, (epochSeconds() - since).toInt())

/** The call didn't get through: nothing was said, so nothing to undo. Offers the ways back (iOS `NotThroughTray`). */
@Composable
fun NotThroughTray(problem: String, onCallAgain: () -> Unit, onShowNotes: () -> Unit) {
    val colors = steerColors()
    Column(
        verticalArrangement = Arrangement.spacedBy(14.dp),
        modifier = Modifier
            .padding(10.dp)
            .fillMaxWidth()
            .background(colors.secondaryBackground, RoundedCornerShape(28.dp))
            .padding(18.dp)
            .testTag("steer.notThrough"),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Icon(Icons.AutoMirrored.Filled.PhoneMissed, contentDescription = null, tint = colors.red, modifier = Modifier.size(20.dp))
            Text("Didn't get through", style = SteerType.headline, color = colors.red)
        }
        Text(problem, style = SteerType.title3, fontWeight = FontWeight.Bold, color = colors.primary)
        Text(
            "Nothing was said on your behalf. Your request is kept, so you can try again when it suits you.",
            style = SteerType.footnote,
            color = colors.secondary,
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(
                onClick = onCallAgain,
                contentPadding = PaddingValues(horizontal = 14.dp, vertical = 10.dp),
                modifier = Modifier.testTag("steer.backToRequest"),
            ) {
                Icon(Icons.AutoMirrored.Filled.Undo, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(6.dp))
                Text("Back to the request")
            }
            Button(
                onClick = onShowNotes,
                contentPadding = PaddingValues(horizontal = 14.dp, vertical = 10.dp),
                modifier = Modifier.testTag("steer.whatHappened"),
            ) {
                Icon(Icons.AutoMirrored.Filled.ListAlt, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(6.dp))
                Text("What happened")
            }
        }
    }
}

/** Times, days and amounts the receptionist said, pinned so they needn't be reread. */
@Composable
fun FactsStrip(facts: List<CallFacts.Fact>) {
    if (facts.isEmpty()) return
    val colors = steerColors()
    Row(
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        modifier = Modifier
            .fillMaxWidth()
            .horizontalScroll(rememberScrollState())
            .padding(start = 20.dp, end = 20.dp, top = 8.dp)
            .testTag("steer.facts")
            .semantics(mergeDescendants = true) {},
    ) {
        facts.forEach { fact ->
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(4.dp),
                modifier = Modifier
                    .background(colors.yellow.copy(alpha = 0.22f), RoundedCornerShape(10.dp))
                    .padding(vertical = 5.dp, horizontal = 9.dp),
            ) {
                Icon(factIcon(fact.kind), contentDescription = null, tint = colors.fact, modifier = Modifier.size(13.dp))
                Text(fact.text, style = SteerType.caption, fontWeight = FontWeight.Bold, color = colors.fact)
            }
        }
    }
}

private fun factIcon(kind: CallFacts.Kind): ImageVector = when (kind) {
    CallFacts.Kind.CLOCK -> Icons.Filled.Schedule
    CallFacts.Kind.CALENDAR -> Icons.Filled.CalendarToday
    CallFacts.Kind.MONEY -> Icons.Filled.CurrencyRupee
}

/** A small capsule pill with a leading icon. */
@Composable
fun StatusPill(text: String, icon: ImageVector, color: Color, modifier: Modifier = Modifier) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        modifier = modifier
            .background(color.copy(alpha = 0.12f), CircleShape)
            .padding(vertical = 7.dp, horizontal = 12.dp)
            .semantics(mergeDescendants = true) {},
    ) {
        Icon(icon, contentDescription = null, tint = color, modifier = Modifier.size(14.dp))
        Text(text, style = SteerType.footnote, fontWeight = FontWeight.SemiBold, color = color)
    }
}
