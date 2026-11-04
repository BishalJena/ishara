package ai.ishara.demo.ui.components

import ai.ishara.demo.recognition.CameraState
import ai.ishara.demo.recognition.LiveCamera
import ai.ishara.demo.ui.theme.IsharaColors
import ai.ishara.demo.ui.theme.IsharaType
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.VideocamOff
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.text
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.min

/** Width / height of the signing video: portrait like the camera frame, cropping a little top and bottom. */
const val VIDEO_ASPECT = 3f / 4f

/**
 * The signing camera beside [side] on the classic call and Brief screens: a portrait video
 * card on the left (40 % of the width, 30 % at accessibility text sizes, and never taller than
 * [maxVideoHeight]) and the panel to its right, so adding chips never moves the video. When
 * the camera is refused, the full permission card (with Open Settings) takes the video's place
 * above [side]. Asks for the camera permission while it is unknown.
 */
@Composable
fun CameraVideoRow(
    camera: LiveCamera?,
    state: CameraState,
    videoTag: String,
    modifier: Modifier = Modifier,
    maxVideoHeight: Dp = Dp.Infinity,
    side: @Composable (Modifier) -> Unit,
) {
    if (cameraContent(camera) == CameraCardContent.Blocked) {
        Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            CameraBlocked(Modifier)
            side(Modifier.fillMaxWidth())
        }
        return
    }
    val fraction = if (isAccessibilityTextSize()) 0.3f else 0.4f
    BoxWithConstraints(modifier.fillMaxWidth()) {
        val videoWidth = min(maxWidth * fraction, maxVideoHeight * VIDEO_ASPECT)
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.Top) {
            CameraVideoCard(camera, state, Modifier.width(videoWidth).aspectRatio(VIDEO_ASPECT).testTag(videoTag), asksPermission = false)
            side(Modifier.weight(1f))
        }
    }
}

/**
 * The live front camera as a rounded card, so the user (and anyone watching) always sees that
 * the camera is on and where their hands are: the mirrored preview with the shoulders, wrists
 * and rest line drawn on it, and the camera state in a chip on the video (green watching,
 * amber signing, red can't see you, which also outlines the card). Without a picture it shows
 * why in the same card: the emulator stand-in (still with the chip, as on the phone), demo
 * mode or no front camera, or a refused permission with a link to Settings. [modifier] sizes
 * it. [asksPermission] is false where the screen asks itself (steer). The chip shows only its
 * dot when [compact] or at accessibility text sizes; TalkBack always reads the full state.
 */
@Composable
fun CameraVideoCard(
    camera: LiveCamera?,
    state: CameraState,
    modifier: Modifier = Modifier,
    asksPermission: Boolean = true,
    compact: Boolean = false,
) {
    val content = cameraContent(camera, asksPermission)
    val showsState = content == CameraCardContent.Live || content == CameraCardContent.Placeholder(CameraPlaceholder.EMULATOR)
    val shape = RoundedCornerShape(16.dp)
    BoxWithConstraints(
        modifier
            .clip(shape)
            .background(IsharaColors.CameraBackdrop)
            .then(
                if (showsState && state == CameraState.CANT_SEE) {
                    Modifier.border(2.dp, IsharaColors.Red, shape)
                } else {
                    // Keeps the card's edge on a pale picture against a pale screen.
                    Modifier.border(1.dp, MaterialTheme.colorScheme.outlineVariant, shape)
                },
            ),
    ) {
        val isSmall = maxWidth < SMALL_VIDEO_WIDTH
        when (content) {
            CameraCardContent.Live -> if (camera != null) {
                Box(Modifier.fillMaxSize().testTag("camera.preview")) {
                    camera.Preview(Modifier.fillMaxSize().semantics { contentDescription = "Camera preview of you" })
                    val showsOverlay by showsBodyOverlay
                    if (showsOverlay) BodyOverlayLayer(camera, Modifier.fillMaxSize(), dotScale = if (isSmall) 0.7f else 1f)
                }
            }
            CameraCardContent.Blocked -> VideoMessage("Camera is off for Ishara.", Icons.Filled.VideocamOff, isSmall, offersSettings = true)
            is CameraCardContent.Placeholder -> VideoMessage(
                content.reason.message,
                if (content.reason == CameraPlaceholder.EMULATOR) Icons.Filled.Person else Icons.Filled.VideocamOff,
                isSmall,
                Modifier.testTag("camera.placeholder"),
            )
        }
        if (showsState) {
            CameraStateChip(
                state,
                showsLabel = !compact && !isAccessibilityTextSize(),
                modifier = Modifier.align(Alignment.TopStart).padding(if (isSmall) 6.dp else 8.dp),
            )
        }
    }
}

/** Below this the card is a thumbnail: smaller dots, smaller message. */
private val SMALL_VIDEO_WIDTH = 120.dp

/**
 * The camera state on the video: a dot in the state colour and a short label on a dark
 * capsule, readable on any picture; solid red when it can't see the user.
 */
@Composable
private fun CameraStateChip(state: CameraState, showsLabel: Boolean, modifier: Modifier) {
    val isAlert = state == CameraState.CANT_SEE
    Row(
        modifier = modifier
            .testTag("camera.pill")
            .clearAndSetSemantics {
                // TalkBack reads the description; the text is what the chip shows.
                contentDescription = "Camera: ${cameraPillTitle(state)}"
                if (showsLabel) text = AnnotatedString(cameraChipLabel(state))
            }
            .background(if (isAlert) IsharaColors.Red else Color.Black.copy(alpha = 0.6f), CircleShape)
            .padding(horizontal = if (showsLabel) 8.dp else 5.dp, vertical = 5.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            Modifier
                .size(8.dp)
                .background(if (isAlert) Color.White else cameraDotColor(state), CircleShape),
        )
        if (showsLabel) {
            Text(
                cameraChipLabel(state),
                color = Color.White,
                style = IsharaType.caption.copy(fontWeight = FontWeight.SemiBold),
                maxLines = 2,
            )
        }
    }
}

/** Green = watching, amber = signing, red = can't see you (WORKFLOW.md), bright enough for the dark chip. */
fun cameraDotColor(state: CameraState): Color = when (state) {
    CameraState.WATCHING -> IsharaColors.Green
    CameraState.SIGNING -> IsharaColors.Orange
    CameraState.CANT_SEE -> IsharaColors.Red
}

fun cameraChipLabel(state: CameraState): String = when (state) {
    CameraState.WATCHING -> "Watching"
    CameraState.SIGNING -> "Signing…"
    CameraState.CANT_SEE -> "Can't see you"
}

/**
 * Says what to do when the camera can't see the user, beside the video (whose chip and outline
 * turn red), in words big enough to read mid-sign.
 */
@Composable
fun CantSeeYouNotice(state: CameraState, modifier: Modifier = Modifier) {
    if (state != CameraState.CANT_SEE) return
    WarningLabel(
        "Can't see you — move back",
        modifier.semantics(mergeDescendants = true) {}.testTag("camera.cantSee"),
        style = IsharaType.headline,
    )
}

/** Why there is no picture, centred in the card; a thumbnail at accessibility sizes keeps just the icon. */
@Composable
private fun VideoMessage(
    message: String,
    icon: ImageVector,
    isSmall: Boolean,
    modifier: Modifier = Modifier,
    offersSettings: Boolean = false,
) {
    val context = LocalContext.current
    val tint = Color.White.copy(alpha = 0.8f)
    val showsText = !(isSmall && isAccessibilityTextSize())
    Box(
        modifier
            .fillMaxSize()
            .semantics(mergeDescendants = true) { if (!showsText) contentDescription = message },
        contentAlignment = Alignment.Center,
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(6.dp),
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 28.dp),
        ) {
            Icon(icon, contentDescription = null, tint = tint, modifier = Modifier.size(if (isSmall) 20.dp else 32.dp))
            if (showsText) {
                Text(message, style = if (isSmall) IsharaType.caption else IsharaType.footnote, color = tint, textAlign = TextAlign.Center)
            }
            if (offersSettings) {
                Text(
                    "Settings",
                    style = IsharaType.caption.copy(fontWeight = FontWeight.Bold),
                    color = Color.White,
                    modifier = Modifier
                        .clickable {
                            context.startActivity(
                                Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", context.packageName, null))
                                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                            )
                        }
                        .padding(8.dp)
                        .testTag("camera.openSettings"),
                )
            }
        }
    }
}
