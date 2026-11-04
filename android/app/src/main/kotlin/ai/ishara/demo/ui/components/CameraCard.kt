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
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
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
 * The camera area of Get ready and the call screens: the live preview with the camera pill on
 * top, a camera-permission message, or a placeholder. Get ready passes no pill state and gets
 * the taller card. A live camera asks for the camera permission here (Android prompts only
 * from an Activity) and reports the answer to recognition.
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
        CameraPermissionRequest(camera)
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

/** The pill keeps its place at the top left of the card; on the call screens the preview sits beside it. */
@Composable
private fun LiveCameraCard(camera: LiveCamera, state: CameraState?, modifier: Modifier) {
    val showsOverlay by showsBodyOverlay
    val isAccessibilitySize = isAccessibilityTextSize()
    val isCallScreen = state != null
    // Get ready is where the user frames themselves, so its preview is the tallest. The call
    // screens keep it small (smaller still at accessibility text sizes) so chips and draft fit.
    val previewHeight = when {
        !isCallScreen -> 360.dp
        isAccessibilitySize -> 120.dp
        else -> 170.dp
    }
    Row(
        modifier = modifier
            .fillMaxWidth()
            .background(IsharaColors.CameraBackdrop, RoundedCornerShape(16.dp))
            .padding(10.dp)
            .testTag("camera.preview"),
        horizontalArrangement = if (isCallScreen) Arrangement.spacedBy(12.dp) else Arrangement.Center,
    ) {
        if (state != null) {
            Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                CameraPill(state)
                if (showsOverlay && !isAccessibilitySize) {
                    Text(
                        "Rest your hands below the dashed line between signs.",
                        style = IsharaType.footnote,
                        color = Color.White.copy(alpha = 0.8f),
                    )
                }
            }
        }
        // Shaped like the camera's portrait frame, so filling it crops nothing: the user sees
        // the whole picture recognition sees, from face down to hands resting on the table.
        Box(
            modifier = Modifier
                .height(previewHeight)
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
        IconLabel("Ishara can't see you", Icons.Filled.Warning, color = Color.White, style = IsharaType.headline)
        Text(
            "Camera access is off for Ishara, so signs can't be recognised. Turn on Camera in Settings.",
            color = Color.White,
            style = IsharaType.callout,
        )
        Button(
            onClick = {
                context.startActivity(
                    Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", context.packageName, null))
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                )
            },
            modifier = Modifier.testTag("camera.openSettings"),
        ) { Text("Open Settings", style = IsharaType.body) }
    }
}

/**
 * Stands in for the live camera when there is none to show: in the emulator, when recognition
 * replays fixed results, or without a front camera. On the call screens (those with a pill) the
 * figure sits beside the message; at accessibility text sizes only the pill is kept there.
 */
@Composable
fun CameraPreviewPlaceholder(state: CameraState?, message: String, modifier: Modifier = Modifier) {
    val isCompact = state != null
    val showsPillOnly = isCompact && isAccessibilityTextSize()
    Column(
        modifier = modifier
            .fillMaxWidth()
            .then(if (isCompact) Modifier else Modifier.heightIn(min = 240.dp))
            .background(IsharaColors.CameraBackdrop, RoundedCornerShape(16.dp))
            .padding(10.dp)
            .semantics(mergeDescendants = true) {},
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        // The pill sits above the placeholder content so it can't cover it when the text grows.
        if (state != null) CameraPill(state)
        if (showsPillOnly) return@Column
        val tint = Color.White.copy(alpha = 0.8f)
        if (isCompact) {
            Row(
                modifier = Modifier.padding(horizontal = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(Icons.Filled.Person, contentDescription = null, tint = tint, modifier = Modifier.size(32.dp))
                Text(message, style = IsharaType.callout, color = tint)
            }
        } else {
            // Centred in the card's 240 dp minimum (less its 10 dp padding).
            Box(Modifier.fillMaxWidth().heightIn(min = 220.dp), contentAlignment = Alignment.Center) {
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Icon(Icons.Filled.Person, contentDescription = null, tint = tint, modifier = Modifier.size(44.dp))
                    Text(message, style = IsharaType.callout, color = tint, textAlign = TextAlign.Center)
                }
            }
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
    Row(
        modifier = modifier
            .background(background, CircleShape)
            .testTag("camera.pill")
            .clearAndSetSemantics { contentDescription = "Camera: $title" }
            .padding(horizontal = 12.dp, vertical = 6.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(10.dp).background(foreground, CircleShape))
        Text(title, color = foreground, style = IsharaType.subheadline.copy(fontWeight = FontWeight.SemiBold))
    }
}

fun cameraPillTitle(state: CameraState): String = when (state) {
    CameraState.WATCHING -> "Watching"
    CameraState.SIGNING -> "Sign in progress"
    CameraState.CANT_SEE -> "Can't see you: move back, hands not visible"
}
