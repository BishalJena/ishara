package ai.ishara.demo.ui.components

import ai.ishara.demo.core.call.Caption
import ai.ishara.demo.ui.theme.IsharaColors
import ai.ishara.demo.ui.theme.IsharaType
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.flow.drop

/**
 * The receptionist's words, the call agent's fixed lines and the user's delivered replies,
 * newest at the bottom. Captions are kept after the call as a read-only transcript.
 */
@Composable
fun CaptionHistory(captions: List<Caption>, modifier: Modifier = Modifier, isCallOver: Boolean = false) {
    val list = rememberLazyListState()
    // Opens on the newest caption (iOS `defaultScrollAnchor(.bottom)`), then follows new ones.
    var hasScrolled by remember { mutableStateOf(false) }
    LaunchedEffect(captions.size) {
        if (captions.isEmpty()) return@LaunchedEffect
        if (hasScrolled) list.animateScrollToItem(captions.size - 1) else list.scrollToItem(captions.size - 1)
        hasScrolled = true
    }
    // The box shrinks when chips or banners appear below it: keep the newest line in view.
    val count by rememberUpdatedState(captions.size)
    LaunchedEffect(list) {
        snapshotFlow { list.layoutInfo.viewportSize.height }.drop(1).collect {
            if (count > 0) list.scrollToItem(count - 1)
        }
    }
    LazyColumn(
        state = list,
        modifier = modifier
            .background(IsharaColors.Teal.copy(alpha = 0.15f), RoundedCornerShape(16.dp))
            .semantics { contentDescription = "Conversation captions" }
            .testTag("call.captions"),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(12.dp),
        // During the call the newest line sits at the bottom, next to the reply, like a chat;
        // the ended transcript reads from the top.
        verticalArrangement = Arrangement.spacedBy(10.dp, if (isCallOver) Alignment.Top else Alignment.Bottom),
    ) {
        if (captions.isEmpty()) {
            item {
                Text(
                    if (isCallOver) "No captions in this call." else "The receptionist's words will appear here.",
                    style = IsharaType.callout,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.testTag("caption.placeholder"),
                )
            }
        }
        // Captions are only ever appended, so the position is a stable key.
        val latestReceptionist = captions.indexOfLast { it.speaker == Caption.Speaker.RECEPTIONIST }
        itemsIndexed(captions, key = { index, _ -> index }) { index, caption -> CaptionRow(caption, isLatest = index == latestReceptionist) }
    }
}

@Composable
private fun CaptionRow(caption: Caption, isLatest: Boolean) {
    when (caption.speaker) {
        // The line being answered stays the largest; earlier ones step down but stay bold.
        Caption.Speaker.RECEPTIONIST -> CaptionLine(
            label = "Receptionist",
            text = caption.text,
            style = (if (isLatest) IsharaType.title3 else IsharaType.body).copy(fontWeight = FontWeight.SemiBold),
            tag = "caption.receptionist",
        )
        Caption.Speaker.USER -> CaptionLine(
            label = "You",
            text = caption.text,
            style = IsharaType.body,
            tag = "caption.you",
            secondary = true,
        )
        // Said by the call agent without a SEND (disclosure, holding line, goodbye): set apart
        // on the right in a quieter style so it never reads as a reply.
        Caption.Speaker.AGENT -> CaptionLine(
            label = "Ishara (voice)",
            text = caption.text,
            style = IsharaType.subheadline.copy(fontStyle = FontStyle.Italic),
            tag = "caption.agent",
            secondary = true,
            trailing = true,
            description = "Ishara voice, said automatically: ${caption.text}",
        )
    }
}

@Composable
private fun CaptionLine(
    label: String,
    text: String,
    style: androidx.compose.ui.text.TextStyle,
    tag: String,
    secondary: Boolean = false,
    trailing: Boolean = false,
    description: String? = null,
) {
    Column(
        horizontalAlignment = if (trailing) Alignment.End else Alignment.Start,
        modifier = Modifier
            .fillMaxWidth()
            .padding(start = if (trailing) 32.dp else 0.dp)
            .testTag(tag)
            .then(if (description != null) Modifier.semantics(mergeDescendants = true) { contentDescription = description } else Modifier.semantics(mergeDescendants = true) {}),
    ) {
        Text(
            label,
            style = IsharaType.caption.copy(fontWeight = FontWeight.SemiBold),
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            text,
            style = style,
            color = if (secondary) MaterialTheme.colorScheme.onSurfaceVariant else MaterialTheme.colorScheme.onSurface,
            textAlign = if (trailing) TextAlign.End else TextAlign.Start,
        )
    }
}
