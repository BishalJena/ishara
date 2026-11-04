package ai.ishara.demo.support

import ai.ishara.demo.recognition.BodyOverlay
import ai.ishara.demo.recognition.CameraPermission
import ai.ishara.demo.recognition.GetReadyModel
import ai.ishara.demo.recognition.LiveCamera
import ai.ishara.demo.recognition.RecognitionController
import ai.ishara.demo.recognition.RecognitionEvent
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.testTag
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.emptyFlow

/**
 * A front camera the test controls. Its preview is a grey box, or [picture] shown like
 * PreviewView shows the camera (aspect-filled, mirrored) so screenshots can judge the look.
 */
class FakeCamera(
    permission: CameraPermission,
    overlay: BodyOverlay? = null,
    private val picture: ImageBitmap? = null,
) : LiveCamera {
    override val permission = MutableStateFlow(permission)
    override val isUnavailable = MutableStateFlow(false)
    override val overlay = MutableStateFlow(overlay)
    val reported = mutableListOf<Boolean>()

    override fun onPermissionResult(granted: Boolean) {
        reported += granted
        permission.value = if (granted) CameraPermission.GRANTED else CameraPermission.DENIED
    }

    @Composable
    override fun Preview(modifier: Modifier) {
        if (picture == null) {
            Box(modifier.background(Color.DarkGray).testTag("fake.preview"))
        } else {
            Image(
                picture,
                contentDescription = null,
                contentScale = ContentScale.Crop,
                modifier = modifier.clipToBounds().graphicsLayer { scaleX = -1f }.testTag("fake.preview"),
            )
        }
    }
}

/** A recognizer that only offers [camera]; nothing is recognised. */
class CameraRecognition(override val camera: LiveCamera? = null) : RecognitionController {
    override val getReady = GetReadyModel()
    override val failure: StateFlow<String?> = MutableStateFlow(null)
    override val notice: StateFlow<String?> = MutableStateFlow(null)
    override val replayOptions: List<String> = emptyList()
    override fun start() = Unit
    override fun signingEvents(): Flow<RecognitionEvent> = emptyFlow()
    override fun replay(option: String) = Unit
    override fun stop() = Unit
}
