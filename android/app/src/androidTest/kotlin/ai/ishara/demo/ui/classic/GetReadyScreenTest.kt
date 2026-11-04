package ai.ishara.demo.ui.classic

import ai.ishara.demo.recognition.BodyOverlay
import ai.ishara.demo.recognition.CameraPermission
import ai.ishara.demo.recognition.GetReadyModel
import ai.ishara.demo.recognition.NormalizedPoint
import ai.ishara.demo.recognition.RecognitionController
import ai.ishara.demo.support.CameraRecognition
import ai.ishara.demo.support.FakeCamera
import ai.ishara.demo.ui.theme.IsharaColors
import ai.ishara.demo.ui.theme.IsharaTheme
import android.Manifest
import androidx.activity.ComponentActivity
import androidx.lifecycle.Lifecycle
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toPixelMap
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import kotlin.math.abs

/**
 * Get ready on its own, with a recognizer the test drives: Start only once every check passed
 * and calibration finished, the camera permission flow, and the body overlay drawn onto the
 * mirrored preview.
 */
@RunWith(AndroidJUnit4::class)
class GetReadyScreenTest {
    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private var started = 0

    private fun show(recognition: RecognitionController) {
        compose.setContent {
            IsharaTheme {
                GetReadyScreen(recognition, "Test mode", "I'm ready, start call", onStart = { started++ }, onBack = {})
            }
        }
    }

    @Test
    fun startStaysOffUntilEveryCheckPassedAndCalibrationFinished() {
        val recognition = CameraRecognition()
        show(recognition)
        val start = compose.onNodeWithTag("getReady.start")
        start.assertIsNotEnabled()

        GetReadyModel.Check.entries.dropLast(1).forEach(recognition.getReady::pass)
        compose.waitForIdle()
        start.assertIsNotEnabled()
        recognition.getReady.pass(GetReadyModel.Check.entries.last())
        compose.waitForIdle()
        start.assertIsNotEnabled()

        recognition.getReady.recordCalibration(1.0)
        compose.onNode(hasText("1.0 s left", substring = true)).assertExists()
        start.assertIsNotEnabled()

        recognition.getReady.recordCalibration(GetReadyModel.CALIBRATION_SECONDS)
        compose.onNode(hasText("Hands at rest: calibrated", substring = true)).assertExists()
        start.assertIsEnabled().performClick()
        assertEquals(1, started)
    }

    @Test
    fun calibrationWaitsForTheChecklist() {
        val recognition = CameraRecognition()
        show(recognition)
        recognition.getReady.recordCalibration(GetReadyModel.CALIBRATION_SECONDS)
        compose.onNode(hasText("Starts once the checklist is done.", substring = true)).assertExists()
        compose.onNodeWithTag("getReady.start").assertIsNotEnabled()
    }

    @Test
    fun refusedCameraExplainsAndOffersSettings() {
        val recognition = CameraRecognition(FakeCamera(CameraPermission.DENIED))
        GetReadyModel.Check.entries.forEach(recognition.getReady::pass)
        show(recognition)
        compose.onNodeWithTag("camera.blocked").assertExists()
        compose.onNode(hasText("Ishara can't see you", substring = true)).assertExists()
        compose.onNodeWithTag("camera.openSettings").assertIsEnabled()
        compose.onNodeWithTag("camera.preview").assertDoesNotExist()
        compose.onNodeWithTag("getReady.start").assertIsNotEnabled()
    }

    /** Refused, then turned on in Settings: back in the app the grant is reported and the preview shows. */
    @Test
    fun grantFromSettingsIsReportedOnReturn() {
        val camera = FakeCamera(CameraPermission.DENIED)
        show(CameraRecognition(camera))
        compose.onNodeWithTag("camera.blocked").assertExists()
        grantCamera()
        compose.activityRule.scenario.moveToState(Lifecycle.State.STARTED)
        compose.activityRule.scenario.moveToState(Lifecycle.State.RESUMED)
        compose.waitUntil(5_000) { camera.reported.isNotEmpty() }
        assertEquals(listOf(true), camera.reported)
        compose.onNodeWithTag("camera.preview").assertExists()
    }

    private fun grantCamera() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        instrumentation.uiAutomation.grantRuntimePermission(instrumentation.targetContext.packageName, Manifest.permission.CAMERA)
    }

    /** A grant the app already has is reported without a prompt, and the live preview shows. */
    @Test
    fun grantedCameraIsReportedAndPreviewed() {
        grantCamera()
        val camera = FakeCamera(CameraPermission.NOT_DETERMINED)
        show(CameraRecognition(camera))
        compose.waitUntil(5_000) { camera.reported.isNotEmpty() }
        assertEquals(listOf(true), camera.reported)
        compose.onNodeWithTag("camera.preview").assertExists()
        compose.onNodeWithTag("fake.preview").assertExists()
    }

    /** The rest line and a wrist land where the user sees them on the mirrored preview. */
    @Test
    fun bodyOverlayIsDrawnOnTheMirroredPreview() {
        // A 9:16 image: the preview shows all of it, so normalized points map straight across.
        val overlay = BodyOverlay(720, 1280, wrists = listOf(NormalizedPoint(0.2f, 0.3f)), restY = 0.75)
        show(CameraRecognition(FakeCamera(CameraPermission.GRANTED, overlay)))
        val pixels = compose.onNodeWithTag("fake.preview").captureToImage().toPixelMap()
        fun isColor(x: Int, y: Int, color: Color) = pixels[x, y].let {
            abs(it.red - color.red) < 0.1f && abs(it.green - color.green) < 0.1f && abs(it.blue - color.blue) < 0.1f
        }
        val restRow = (0.75f * pixels.height).toInt()
        val orangeInRestRow = (0 until pixels.width).count { x -> (restRow - 2..restRow + 2).any { isColor(x, it, IsharaColors.Orange) } }
        assertTrue("no dashed rest line at 75 % height", orangeInRestRow > pixels.width / 3)
        // Mirrored: the wrist at 20 % from the image's left shows 80 % across the preview.
        assertTrue("the wrist isn't drawn mirrored", isColor((0.8f * pixels.width).toInt(), (0.3f * pixels.height).toInt(), IsharaColors.Yellow))
        assertTrue("the wrist was drawn unmirrored", !isColor((0.2f * pixels.width).toInt(), (0.3f * pixels.height).toInt(), IsharaColors.Yellow))
    }
}
