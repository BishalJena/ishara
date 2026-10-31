package ai.ishara.demo.ui.classic

import ai.ishara.demo.app.DemoFixture
import ai.ishara.demo.app.makeActiveCall
import ai.ishara.demo.call.ActiveCallViewModel
import ai.ishara.demo.core.call.Brief
import ai.ishara.demo.core.call.CallMode
import ai.ishara.demo.core.call.CallState
import ai.ishara.demo.core.call.ServerMessage
import ai.ishara.demo.core.call.onMain
import ai.ishara.demo.models.CallSetup
import ai.ishara.demo.models.Delegation
import ai.ishara.demo.recognition.CameraPermission
import ai.ishara.demo.recognition.CameraState
import ai.ishara.demo.recognition.LiveCamera
import ai.ishara.demo.recognition.RecognitionEvent
import ai.ishara.demo.support.CameraRecognition
import ai.ishara.demo.support.FakeCamera
import ai.ishara.demo.support.RecordingDriver
import ai.ishara.demo.support.eventually
import ai.ishara.demo.ui.components.LocalRunsInEmulator
import ai.ishara.demo.ui.components.cameraPillTitle
import ai.ishara.demo.ui.steer.SteerCallScreen
import ai.ishara.demo.ui.theme.IsharaColors
import ai.ishara.demo.ui.theme.IsharaTheme
import android.Manifest
import androidx.activity.ComponentActivity
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toPixelMap
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.assert
import androidx.compose.ui.test.assertContentDescriptionEquals
import androidx.compose.ui.test.assertTextEquals
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.getBoundsInRoot
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.width
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import kotlin.math.abs

/**
 * The live signing video on the call, Brief and steer screens, with a camera the test drives:
 * the mirrored preview in a card with the camera state on it, the permission card when the
 * camera is refused, the placeholder without a camera, and the video kept (smaller) at the
 * largest font scale.
 */
@RunWith(AndroidJUnit4::class)
class CameraVideoUiTest {
    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private fun show(fontScale: Float = 1f, isEmulator: Boolean = false, content: @Composable () -> Unit) {
        compose.setContent {
            val density = LocalDensity.current
            CompositionLocalProvider(
                LocalDensity provides Density(density.density, fontScale),
                LocalRunsInEmulator provides isEmulator,
            ) { IsharaTheme(darkTheme = false) { content() } }
        }
    }

    private fun call(fixture: DemoFixture, camera: LiveCamera?): ActiveCallViewModel =
        runBlocking { withContext(Dispatchers.Main) { fixture.makeActiveCall(CameraRecognition(camera))!! } }

    private fun showCall(model: ActiveCallViewModel, fontScale: Float = 1f, isEmulator: Boolean = false) =
        show(fontScale, isEmulator) { ActiveCallScreen(model, onLeave = {}, onShowNotes = null) }

    private fun liveCamera() = FakeCamera(CameraPermission.GRANTED)

    private fun hasColor(tag: String, color: Color): Boolean {
        val pixels = compose.onNodeWithTag(tag).captureToImage().toPixelMap()
        return (0 until pixels.width).any { x ->
            (0 until pixels.height).any { y ->
                pixels[x, y].let { abs(it.red - color.red) < 0.06f && abs(it.green - color.green) < 0.06f && abs(it.blue - color.blue) < 0.06f }
            }
        }
    }

    private fun assertChip(state: CameraState, label: String?) {
        val chip = compose.onNodeWithTag("camera.pill").assertContentDescriptionEquals("Camera: ${cameraPillTitle(state)}")
        if (label != null) chip.assertTextEquals(label) else assertTrue(chip.fetchSemanticsNode().config.getOrNull(SemanticsProperties.Text).isNullOrEmpty())
    }

    @Test
    fun signingCallShowsTheLiveVideoWithTheCameraStateOnIt() {
        val model = call(DemoFixture.SIGNING, liveCamera())
        showCall(model)
        compose.onNodeWithTag("call.camera").assertExists()
        compose.onNodeWithTag("fake.preview", useUnmergedTree = true).assertExists()
        // The chips sit beside the video, not under it.
        val video = compose.onNodeWithTag("call.camera").getBoundsInRoot()
        val chip = compose.onNodeWithTag("chip.no").getBoundsInRoot()
        assertTrue("the chips $chip aren't beside the video $video", chip.left >= video.right && chip.top < video.bottom)

        assertChip(CameraState.SIGNING, "Signing…")
        assertTrue("the signing dot isn't amber", hasColor("camera.pill", IsharaColors.Orange))
        compose.onNodeWithTag("camera.cantSee").assertDoesNotExist()

        onMain { model.handle(RecognitionEvent.Camera(CameraState.WATCHING)) }
        assertChip(CameraState.WATCHING, "Watching")
        assertTrue("the watching dot isn't green", hasColor("camera.pill", IsharaColors.Green))
        assertFalse("the card is outlined red while watching", hasColor("call.camera", IsharaColors.Red))

        onMain { model.handle(RecognitionEvent.Camera(CameraState.CANT_SEE)) }
        assertChip(CameraState.CANT_SEE, "Can't see you")
        assertTrue("the can't-see chip isn't red", hasColor("camera.pill", IsharaColors.Red))
        compose.onNodeWithTag("camera.cantSee").assertExists().assert(hasText("Can't see you — move back"))
    }

    /** The red outline is on the card itself, not only the chip. */
    @Test
    fun cantSeeYouOutlinesTheVideoInRed() {
        val model = call(DemoFixture.SIGNING, liveCamera())
        onMain { model.handle(RecognitionEvent.Camera(CameraState.CANT_SEE)) }
        showCall(model)
        val pixels = compose.onNodeWithTag("call.camera").captureToImage().toPixelMap()
        val edge = pixels[0, pixels.height / 2]
        assertTrue("the card's edge $edge isn't red", abs(edge.red - IsharaColors.Red.red) < 0.06f && abs(edge.green - IsharaColors.Red.green) < 0.06f)
    }

    /** While a reply is spoken the same video stays, beside the notices, with STOP in reach. */
    @Test
    fun speakingKeepsTheVideo() {
        val model = call(DemoFixture.SPEAKING, liveCamera())
        showCall(model)
        compose.onNodeWithTag("call.stop").assertExists()
        compose.onNodeWithTag("call.camera").assertExists()
        compose.onNodeWithTag("fake.preview", useUnmergedTree = true).assertExists()
        assertChip(CameraState.WATCHING, "Watching")
    }

    @Test
    fun refusedCameraShowsThePermissionCardInsteadOfTheVideo() {
        val model = call(DemoFixture.SIGNING, FakeCamera(CameraPermission.DENIED))
        showCall(model)
        compose.onNodeWithTag("camera.blocked").assertExists()
        compose.onNodeWithTag("camera.openSettings").assertExists()
        compose.onNodeWithTag("call.camera").assertDoesNotExist()
        compose.onNodeWithTag("chip.no").assertExists()
    }

    /** The emulator's stand-in keeps the card (and its chip) where the phone shows the video. */
    @Test
    fun withoutACameraTheEmulatorShowsAPlaceholderInTheVideosPlace() {
        showCall(call(DemoFixture.SIGNING, camera = null), isEmulator = true)
        compose.onNodeWithTag("call.camera").assertExists()
        compose.onNodeWithTag("camera.placeholder").assert(hasText("Camera preview appears on your phone."))
        assertChip(CameraState.SIGNING, "Signing…")
    }

    /** With no camera at all (demo mode) the card says so and claims no camera state. */
    @Test
    fun demoModeSaysTheCameraIsOffWithoutAState() {
        showCall(call(DemoFixture.SIGNING, camera = null))
        compose.onNodeWithTag("camera.placeholder").assert(hasText("Camera is off in demo mode."))
        compose.onNodeWithTag("camera.pill").assertDoesNotExist()
    }

    /** At the largest font the video stays, narrower, and the chip keeps only its dot (TalkBack still reads the state). */
    @Test
    fun videoStaysSmallerAtTheLargestFontScale() {
        val model = call(DemoFixture.SIGNING, liveCamera())
        showCall(model, fontScale = 2f)
        val screen = compose.onRoot().getBoundsInRoot()
        val video = compose.onNodeWithTag("call.camera").assertExists().getBoundsInRoot()
        compose.onNodeWithTag("fake.preview", useUnmergedTree = true).assertExists()
        assertTrue("the video $video isn't the compact one", video.width < screen.width * 0.34f)
        assertTrue("the video $video is a sliver", video.width > screen.width * 0.2f)
        assertChip(CameraState.SIGNING, label = null)
        compose.onNodeWithTag("call.send").assertExists()
    }

    @Test
    fun briefShowsTheVideoBesideWhatWasSigned() {
        val model = onMain { BriefModel(CallSetup.demo, RecordingDriver(), CameraRecognition(liveCamera())) }
        show { BriefScreen(model, modeDescription = "Test mode", onApprove = {}, onBack = {}) }
        compose.onNodeWithTag("brief.camera").assertExists()
        compose.onNodeWithTag("fake.preview", useUnmergedTree = true).assertExists()
        assertChip(CameraState.WATCHING, "Watching")
        onMain { model.handle(RecognitionEvent.Camera(CameraState.CANT_SEE)) }
        assertChip(CameraState.CANT_SEE, "Can't see you")
        compose.onNodeWithTag("camera.cantSee").assertExists()
    }

    @Test
    fun steerSigningPanelShowsTheVideoWithAStateDot() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        // The steer screen asks the system for the camera itself.
        instrumentation.uiAutomation.grantRuntimePermission(instrumentation.targetContext.packageName, Manifest.permission.CAMERA)
        val brief = Brief("b1", "Call on behalf of Riya.", "book a doctor's appointment", emptyList())
        val setup = CallSetup.demo.copy(delegation = Delegation(brief, attended = false, mode = CallMode.STEER), request = "Book a doctor's appointment")
        val driver = onMain { RecordingDriver() }
        val model = onMain { ActiveCallViewModel(setup, driver, CameraRecognition(liveCamera())) }
        runBlocking { withContext(Dispatchers.Main) { model.start() } }
        onMain { driver.store.receive(ServerMessage.Status(CallState.IN_CALL)) }
        assertTrue(eventually { model.phase == ActiveCallViewModel.Phase.Live })
        show { SteerCallScreen(model, onLeave = {}, onShowNotes = {}) }
        compose.onNodeWithTag("steer.sign").performClick()
        compose.onNodeWithTag("steer.camera").assertExists()
        compose.onNodeWithTag("fake.preview", useUnmergedTree = true).assertExists()
        assertChip(CameraState.WATCHING, label = null)
        onMain { model.handle(RecognitionEvent.Camera(CameraState.SIGNING)) }
        assertTrue("the signing dot isn't amber", hasColor("camera.pill", IsharaColors.Orange))
    }
}
