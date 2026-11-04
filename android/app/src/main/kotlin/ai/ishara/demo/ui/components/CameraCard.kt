package ai.ishara.demo.ui.components

import ai.ishara.demo.recognition.BodyOverlay
import ai.ishara.demo.recognition.CameraPermission
import ai.ishara.demo.recognition.CameraState
import ai.ishara.demo.recognition.LiveCamera
import ai.ishara.demo.recognition.PreviewMapping
import ai.ishara.demo.ui.theme.IsharaColors
import ai.ishara.demo.ui.theme.IsharaType
import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Face
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Videocam
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LifecycleResumeEffect

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

/** Tracking dots on or off, for every camera card of the run (iOS keeps it in `@AppStorage`). */
private val showsBodyOverlay = mutableStateOf(true)

/**
 * Get ready's camera area, where the user frames themselves: the live preview, a camera-permission
 * message, or a placeholder. The call screens show only [CameraIndicator]. A live camera asks
 * for the camera permission here (Android prompts only from an Activity) and reports the answer
 * to recognition.
 */
@Composable
fun CameraCard(camera: LiveCamera?, modifier: Modifier = Modifier) {
    when (val content = cameraContent(camera)) {
        CameraCardContent.Live -> if (camera != null) LiveCameraCard(camera, modifier)
        CameraCardContent.Blocked -> CameraBlocked(modifier)
        is CameraCardContent.Placeholder -> CameraPreviewPlaceholder(content.reason.message, modifier)
    }
}

/** What to show for [camera], asking for the permission while it is unknown. */
@Composable
private fun cameraContent(camera: LiveCamera?, isEmulator: Boolean = LocalRunsInEmulator.current): CameraCardContent {
    if (camera == null) return CameraCardContent.of(null, isEmulator)
    CameraPermissionRequest(camera)
    // Read as state so the screens follow permission changes.
    camera.permission.collectAsState().value
    camera.isUnavailable.collectAsState().value
    return CameraCardContent.of(camera, isEmulator)
}

/**
 * The call screens' small camera indicator: a green camera while recognition watches, amber
 * with "Signing…" while a sign is in progress, red when it can't see the user (the panel then
 * says what to do, see [CallCameraNotice]). TalkBack reads the full camera state.
 */
@Composable
fun CameraIndicator(state: CameraState, modifier: Modifier = Modifier) {
    val color = cameraStateColor(state)
    val label = if (state == CameraState.SIGNING && !isAccessibilityTextSize()) "Signing…" else null
    Row(
        modifier = modifier
            .testTag("camera.pill")
            .clearAndSetSemantics { contentDescription = "Camera: ${cameraPillTitle(state)}" }
            .background(color.copy(alpha = 0.15f), CircleShape)
            .padding(horizontal = if (label == null) 6.dp else 10.dp, vertical = 6.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(Icons.Filled.Videocam, contentDescription = null, tint = color, modifier = Modifier.size(20.dp))
        if (label != null) Text(label, color = color, style = IsharaType.footnote.copy(fontWeight = FontWeight.SemiBold))
    }
}

/**
 * What the call screens say about the camera beside the indicator: the permission card when it
 * is refused, why there is no picture on a phone without a front camera, and what to do when it
 * can't see the user. Also asks for the permission, like Get ready's card.
 */
@Composable
fun CallCameraNotice(camera: LiveCamera?, state: CameraState, modifier: Modifier = Modifier) {
    val content = cameraContent(camera)
    Column(modifier, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        if (content == CameraCardContent.Blocked) CameraBlocked(Modifier)
        if (content == CameraCardContent.Placeholder(CameraPlaceholder.NO_CAMERA)) {
            WarningLabel(CameraPlaceholder.NO_CAMERA.message, style = IsharaType.subheadline)
        }
        if (state == CameraState.CANT_SEE) {
            WarningLabel(
                "Can't see you — move back",
                Modifier.semantics(mergeDescendants = true) {}.testTag("camera.cantSee"),
                style = IsharaType.headline,
            )
        }
    }
}

/** Green = watching, amber = signing, red = can't see you (WORKFLOW.md), readable on the screen's background. */
@Composable
fun cameraStateColor(state: CameraState): Color = when (state) {
    CameraState.WATCHING -> MaterialTheme.colorScheme.primary
    CameraState.SIGNING -> if (MaterialTheme.colorScheme.background.luminance() < 0.5f) IsharaColors.Orange else DarkAmber
    CameraState.CANT_SEE -> IsharaColors.Red
}

/** Amber dark enough for text on white (4.6:1). */
private val DarkAmber = Color(0xFFA85A00)

/**
 * Asks for CAMERA while the answer is unknown (or reports a grant the app already has), and on
 * a return to the app reports a grant made in Settings meanwhile. (Revoking it there restarts
 * the app, so there is no change the other way to report.)
 */
@Composable
private fun CameraPermissionRequest(camera: LiveCamera) {
    val context = LocalContext.current
    val permission by camera.permission.collectAsState()
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        camera.onPermissionResult(granted)
    }
    LaunchedEffect(camera, permission) {
        if (permission != CameraPermission.NOT_DETERMINED) return@LaunchedEffect
        if (hasCameraPermission(context)) camera.onPermissionResult(true) else launcher.launch(Manifest.permission.CAMERA)
    }
    // Only after the app was left (to Settings, say): until then the prompt's answer stands.
    var wasPaused by remember(camera) { mutableStateOf(false) }
    LifecycleResumeEffect(camera) {
        if (wasPaused && hasCameraPermission(context) && camera.permission.value == CameraPermission.DENIED) {
            camera.onPermissionResult(true)
        }
        onPauseOrDispose { wasPaused = true }
    }
}

private fun hasCameraPermission(context: Context): Boolean =
    ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED

/** Get ready's preview, tall enough to frame face to hands, with the tracking-dots toggle. */
@Composable
private fun LiveCameraCard(camera: LiveCamera, modifier: Modifier) {
    val showsOverlay by showsBodyOverlay
    Row(
        modifier = modifier
            .fillMaxWidth()
            .background(IsharaColors.CameraBackdrop, RoundedCornerShape(16.dp))
            .padding(10.dp)
            .testTag("camera.preview"),
        horizontalArrangement = Arrangement.Center,
    ) {
        // Shaped like the camera's portrait frame, so filling it crops nothing: the user sees
        // the whole picture recognition sees, from face down to hands resting on the table.
        Box(
            modifier = Modifier
                .height(PREVIEW_HEIGHT)
                .aspectRatio(FRAME_ASPECT)
                .clip(RoundedCornerShape(12.dp))
                .background(Color.Black),
        ) {
            camera.Preview(Modifier.fillMaxSize().semantics { contentDescription = "Camera preview of you" })
            if (showsOverlay) BodyOverlayLayer(camera, Modifier.fillMaxSize())
            IconButton(
                onClick = { showsBodyOverlay.value = !showsBodyOverlay.value },
                modifier = Modifier
                    .align(Alignment.TopEnd)
                    .testTag("camera.overlayToggle")
                    .semantics { contentDescription = if (showsOverlay) "Hide tracking dots" else "Show tracking dots" },
            ) {
                Box(
                    Modifier.size(30.dp).background(Color.White.copy(alpha = 0.75f), CircleShape),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(
                        if (showsOverlay) Icons.Filled.Person else Icons.Filled.Face,
                        contentDescription = null,
                        tint = Color.Black,
                        modifier = Modifier.size(18.dp),
                    )
                }
            }
        }
    }
}

private val PREVIEW_HEIGHT = 300.dp

/** True on the emulator, which has no camera; the app root provides it. */
val LocalRunsInEmulator = staticCompositionLocalOf { false }

/** Width / height of the upright front-camera frame (720×1280). */
const val FRAME_ASPECT = 9f / 16f

/**
 * Dots on the tracked shoulders and wrists, and a dashed rest line once calibration has found
 * it: lift a hand above the line to start a sign. Reads `camera.overlay` here only, so new
 * frames redraw this layer and nothing else.
 */
@Composable
fun BodyOverlayLayer(camera: LiveCamera, modifier: Modifier = Modifier) {
    val overlay by camera.overlay.collectAsState()
    Canvas(modifier.clearAndSetSemantics {}) { overlay?.let { draw(it) } }
}

private fun DrawScope.draw(overlay: BodyOverlay) {
    val mapping = PreviewMapping.of(overlay, size.width, size.height)
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
    overlay.shoulders.forEach { point ->
        val (x, y) = mapping.point(point)
        drawCircle(Color.White, 5.dp.toPx(), Offset(x, y))
    }
    overlay.wrists.forEach { point ->
        val (x, y) = mapping.point(point)
        drawCircle(IsharaColors.Yellow, 8.dp.toPx(), Offset(x, y))
        drawCircle(Color.Black.copy(alpha = 0.6f), 8.dp.toPx(), Offset(x, y), style = Stroke(1.5.dp.toPx()))
    }
}

/**
 * Camera permission is refused: say so plainly and offer the app's settings. Recognition
 * can't run, so nothing will be recognised or sent.
 */
@Composable
private fun CameraBlocked(modifier: Modifier) {
    val context = LocalContext.current
    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(IsharaColors.CameraBackdrop, RoundedCornerShape(16.dp))
            .padding(14.dp)
            .testTag("camera.blocked"),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        IconLabel("Ishara can't see you", Icons.Filled.Warning, color = Color.White, style = IsharaType.headline)
        Text(
            "Camera access is off for Ishara, so signs can't be recognised. Turn on Camera in Settings.",
            color = Color.White,
            style = IsharaType.callout,
        )
        TonalButton(
            "Open Settings",
            {
                context.startActivity(
                    Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", context.packageName, null))
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                )
            },
            Modifier.testTag("camera.openSettings"),
            tint = Color.White,
        )
    }
}

/**
 * Stands in for the live camera on Get ready when there is none to show: in the emulator, when
 * recognition replays fixed results, or without a front camera.
 */
@Composable
private fun CameraPreviewPlaceholder(message: String, modifier: Modifier = Modifier) {
    val tint = Color.White.copy(alpha = 0.8f)
    Box(
        modifier = modifier
            .fillMaxWidth()
            .heightIn(min = 220.dp)
            .background(IsharaColors.CameraBackdrop, RoundedCornerShape(16.dp))
            .padding(10.dp)
            .semantics(mergeDescendants = true) {},
        contentAlignment = Alignment.Center,
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Icon(Icons.Filled.Person, contentDescription = null, tint = tint, modifier = Modifier.size(44.dp))
            Text(message, style = IsharaType.callout, color = tint, textAlign = TextAlign.Center)
        }
    }
}

fun cameraPillTitle(state: CameraState): String = when (state) {
    CameraState.WATCHING -> "Watching"
    CameraState.SIGNING -> "Sign in progress"
    CameraState.CANT_SEE -> "Can't see you: move back, hands not visible"
}
