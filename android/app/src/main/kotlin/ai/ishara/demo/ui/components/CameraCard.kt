package ai.ishara.demo.ui.components

import ai.ishara.demo.recognition.BodyOverlay
import ai.ishara.demo.recognition.CameraPermission
import ai.ishara.demo.recognition.CameraState
import ai.ishara.demo.recognition.LiveCamera
import ai.ishara.demo.recognition.NormalizedPoint
import ai.ishara.demo.ui.theme.IsharaColors
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlin.math.max

/** What the camera area shows. */
sealed interface CameraCardContent {
    /** The live front camera (also while the permission prompt is up). */
    data object Live : CameraCardContent

    /** The camera is refused. */
    data object Blocked : CameraCardContent

    /** Nothing live to show; the message says why. */
    data class Placeholder(val reason: CameraPlaceholder) : CameraCardContent

    companion object {
        /** A live camera wins whenever recognition watches one; without one the placeholder stays. */
        fun of(camera: LiveCamera?, isEmulator: Boolean): CameraCardContent {
            if (camera == null) return Placeholder(if (isEmulator) CameraPlaceholder.EMULATOR else CameraPlaceholder.CAMERA_OFF)
            if (camera.isUnavailable.value) return Placeholder(CameraPlaceholder.NO_CAMERA)
            return when (camera.permission.value) {
                CameraPermission.DENIED -> Blocked
                CameraPermission.GRANTED, CameraPermission.NOT_DETERMINED -> Live
            }
        }
    }
}

enum class CameraPlaceholder(val message: String) {
    /** The emulator has no camera. */
    EMULATOR("Camera preview appears on your phone."),

    /** Recognition replays fixed results, so the camera isn't used. */
    CAMERA_OFF("Camera is off in demo mode."),

    /** The device has no usable front camera. */
    NO_CAMERA("No front camera found on this phone."),
}

/**
 * Maps normalized points of the upright camera image onto a view that shows that image
 * aspect-filled and, for the front camera, mirrored.
 */
data class PreviewMapping(val imageSize: Size, val viewSize: Size, val mirrored: Boolean = true) {
    private val shown: Size
        get() {
            val scale = max(viewSize.width / imageSize.width, viewSize.height / imageSize.height)
            return Size(imageSize.width * scale, imageSize.height * scale)
        }

    fun point(normalized: NormalizedPoint): Offset {
        val shown = shown
        val x = if (mirrored) 1 - normalized.x else normalized.x
        return Offset((viewSize.width - shown.width) / 2 + x * shown.width, (viewSize.height - shown.height) / 2 + normalized.y * shown.height)
    }

    fun y(normalizedY: Double): Float = point(NormalizedPoint(0f, normalizedY.toFloat())).y
}

/**
 * The camera area of Get ready and the call screens: the live preview with the camera pill on
 * top, a camera-permission message, or a placeholder. Get ready passes no pill state and gets
 * the taller card.
 */
@Composable
fun CameraCard(
    camera: LiveCamera?,
    state: CameraState?,
    modifier: Modifier = Modifier,
    isEmulator: Boolean = LocalRunsInEmulator.current,
) {
    val content = if (camera == null) {
        CameraCardContent.of(null, isEmulator)
    } else {
        // Read as state so the card follows permission changes.
        camera.permission.collectAsState().value
        camera.isUnavailable.collectAsState().value
        CameraCardContent.of(camera, isEmulator)
    }
    when (content) {
        CameraCardContent.Live -> if (camera != null) LiveCameraCard(camera, state, modifier)
        CameraCardContent.Blocked -> CameraBlocked(state, modifier)
        is CameraCardContent.Placeholder -> CameraPreviewPlaceholder(state, content.reason.message, modifier)
    }
}

@Composable
private fun LiveCameraCard(camera: LiveCamera, state: CameraState?, modifier: Modifier) {
    var showsOverlay by rememberSaveable { mutableStateOf(true) }
    val isCallScreen = state != null
    Row(
        modifier = modifier
            .fillMaxWidth()
            .background(IsharaColors.CameraBackdrop, RoundedCornerShape(16.dp))
            .padding(10.dp)
            .testTag("camera.preview"),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        if (state != null) {
            Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                CameraPill(state)
                if (showsOverlay) {
                    Text(
                        "Rest your hands below the dashed line between signs.",
                        style = MaterialTheme.typography.bodySmall,
                        color = Color.White.copy(alpha = 0.8f),
                    )
                }
            }
        }
        // Shaped like the camera's portrait frame, so filling it crops nothing.
        Box(
            modifier = Modifier
                .height(if (isCallScreen) 170.dp else 360.dp)
                .aspectRatio(FRAME_ASPECT)
                .clip(RoundedCornerShape(12.dp))
                .background(Color.Black),
        ) {
            camera.Preview(Modifier.fillMaxSize().semantics { contentDescription = "Camera preview of you" })
            if (showsOverlay) BodyOverlayLayer(camera, Modifier.fillMaxSize())
            TextButton(
                onClick = { showsOverlay = !showsOverlay },
                modifier = Modifier
                    .align(Alignment.TopEnd)
                    .testTag("camera.overlayToggle")
                    .semantics { contentDescription = if (showsOverlay) "Hide tracking dots" else "Show tracking dots" },
            ) { Text(if (showsOverlay) "●" else "○", color = Color.White) }
        }
    }
}

/** True on the emulator, which has no camera; the app root provides it. */
val LocalRunsInEmulator = staticCompositionLocalOf { false }

/** Width / height of the upright front-camera frame (720×1280). */
const val FRAME_ASPECT = 9f / 16f

/**
 * Dots on the tracked shoulders and wrists, and a dashed rest line once calibration has found
 * it. Reads `camera.overlay` here only, so new frames redraw this layer and nothing else.
 */
@Composable
fun BodyOverlayLayer(camera: LiveCamera, modifier: Modifier = Modifier) {
    val overlay by camera.overlay.collectAsState()
    Canvas(modifier) { overlay?.let { draw(it) } }
}

private fun androidx.compose.ui.graphics.drawscope.DrawScope.draw(overlay: BodyOverlay) {
    val mapping = PreviewMapping(Size(overlay.imageWidth.toFloat(), overlay.imageHeight.toFloat()), size)
    overlay.restY?.let { restY ->
        val y = mapping.y(restY)
        drawLine(
            IsharaColors.Orange,
            Offset(0f, y),
            Offset(size.width, y),
            strokeWidth = 2.dp.toPx(),
            pathEffect = PathEffect.dashPathEffect(floatArrayOf(8.dp.toPx(), 6.dp.toPx())),
        )
    }
    overlay.shoulders.forEach { drawCircle(Color.White, 5.dp.toPx(), mapping.point(it)) }
    overlay.wrists.forEach {
        val center = mapping.point(it)
        drawCircle(IsharaColors.Yellow, 8.dp.toPx(), center)
        drawCircle(Color.Black.copy(alpha = 0.6f), 8.dp.toPx(), center, style = Stroke(1.5.dp.toPx()))
    }
}

/**
 * Camera permission is refused: say so plainly and offer the app's settings. Recognition
 * can't run, so nothing will be recognised or sent.
 */
@Composable
private fun CameraBlocked(state: CameraState?, modifier: Modifier) {
    val context = LocalContext.current
    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(IsharaColors.CameraBackdrop, RoundedCornerShape(16.dp))
            .padding(16.dp)
            .testTag("camera.blocked"),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        if (state != null) CameraPill(state)
        Text("Ishara can't see you", color = Color.White, style = MaterialTheme.typography.titleMedium)
        Text(
            "Camera access is off for Ishara, so signs can't be recognised. Turn on Camera in Settings.",
            color = Color.White,
            style = MaterialTheme.typography.bodyMedium,
        )
        Button(
            onClick = {
                context.startActivity(
                    Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", context.packageName, null)),
                )
            },
            modifier = Modifier.testTag("camera.openSettings"),
        ) { Text("Open Settings") }
    }
}

/** Stands in for the live camera when there is none to show. */
@Composable
fun CameraPreviewPlaceholder(state: CameraState?, message: String, modifier: Modifier = Modifier) {
    val isCompact = state != null
    Column(
        modifier = modifier
            .fillMaxWidth()
            .then(if (isCompact) Modifier else Modifier.heightIn(min = 240.dp))
            .background(IsharaColors.CameraBackdrop, RoundedCornerShape(16.dp))
            .padding(10.dp)
            .testTag("call.camera"),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        // The pill sits above the placeholder content so it can't cover it when the text grows.
        if (state != null) CameraPill(state)
        val content: @Composable () -> Unit = {
            Text("🧍", style = MaterialTheme.typography.headlineMedium, color = Color.White.copy(alpha = 0.8f))
            Text(message, style = MaterialTheme.typography.bodyMedium, color = Color.White.copy(alpha = 0.8f))
        }
        if (isCompact) {
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) { content() }
        } else {
            Column(
                modifier = Modifier.fillMaxWidth().weight(1f, fill = false),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) { content() }
        }
    }
}

/** Green = watching, yellow = signing, red = can't see you (WORKFLOW.md). */
@Composable
fun CameraPill(state: CameraState, modifier: Modifier = Modifier) {
    val title = cameraPillTitle(state)
    val background = when (state) {
        CameraState.WATCHING -> IsharaColors.Green
        CameraState.SIGNING -> IsharaColors.Yellow
        CameraState.CANT_SEE -> IsharaColors.Red
    }
    val foreground = if (state == CameraState.SIGNING) Color.Black else Color.White
    Text(
        "● $title",
        color = foreground,
        style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.SemiBold),
        modifier = modifier
            .widthIn(max = 360.dp)
            .background(background, CircleShape)
            .padding(horizontal = 12.dp, vertical = 6.dp)
            .semantics { contentDescription = "Camera: $title" }
            .testTag("camera.pill"),
    )
}

fun cameraPillTitle(state: CameraState): String = when (state) {
    CameraState.WATCHING -> "Watching"
    CameraState.SIGNING -> "Sign in progress"
    CameraState.CANT_SEE -> "Can't see you: move back, hands not visible"
}
