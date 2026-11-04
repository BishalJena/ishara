package ai.ishara.demo.ui.classic

import ai.ishara.demo.app.DemoFixture
import ai.ishara.demo.app.makeActiveCall
import ai.ishara.demo.call.ActiveCallViewModel
import ai.ishara.demo.core.call.Brief
import ai.ishara.demo.core.call.CallState
import ai.ishara.demo.core.call.ServerMessage
import ai.ishara.demo.core.call.Sign
import ai.ishara.demo.core.call.onMain
import ai.ishara.demo.core.call.CallMode
import ai.ishara.demo.models.CallSetup
import ai.ishara.demo.models.Delegation
import ai.ishara.demo.recognition.BodyOverlay
import ai.ishara.demo.recognition.CameraPermission
import ai.ishara.demo.recognition.CameraState
import ai.ishara.demo.recognition.RecognitionEvent
import ai.ishara.demo.recognition.RecognitionResult
import ai.ishara.demo.recognition.pipeline.BitmapFrame
import ai.ishara.demo.recognition.pipeline.HolisticLandmarkProvider
import ai.ishara.demo.recognition.pipeline.bodyOverlay
import ai.ishara.demo.support.CameraRecognition
import ai.ishara.demo.support.FakeCamera
import ai.ishara.demo.support.RecordingDriver
import ai.ishara.demo.support.eventually
import ai.ishara.demo.ui.steer.SteerCallScreen
import ai.ishara.demo.ui.theme.IsharaTheme
import android.Manifest
import android.graphics.Bitmap
import android.media.MediaMetadataRetriever
import androidx.activity.ComponentActivity
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Modifier
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.unit.Density
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * Screenshots of the signing video on the call, Brief and steer screens, light and dark, with
 * a frame of a debug sample clip standing in for the camera (and its real Holistic overlay).
 * Only with the instrumentation argument `cameraScreenshots true`; saved under the app's
 * external files in `camera-screenshots`. Needs the debug sample clips and the Holistic model.
 */
@RunWith(AndroidJUnit4::class)
class CameraVideoScreenshots {
    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private val app get() = InstrumentationRegistry.getInstrumentation().targetContext
    private val dark = mutableStateOf(false)
    private val fontScale = mutableStateOf(1f)
    private val screen = mutableStateOf<(@Composable () -> Unit)?>(null)

    // A plain return, not an assumption: AGP 9 reports skipped assumptions as failed tests.
    private val asked = InstrumentationRegistry.getArguments().getString("cameraScreenshots") == "true"

    @Before
    fun onlyWhenAsked() {
        if (!asked) return
        // The steer screen asks the system itself.
        InstrumentationRegistry.getInstrumentation().uiAutomation.grantRuntimePermission(app.packageName, Manifest.permission.CAMERA)
        compose.setContent {
            val density = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(density.density, fontScale.value)) {
                IsharaTheme(darkTheme = dark.value) {
                    Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) { screen.value?.invoke() }
                }
            }
        }
    }

    private class Shot(val picture: Bitmap, val overlay: BodyOverlay)

    /** A 3:4 crop of a clip frame, [zoom] times closer, centred on the signer, with its tracked overlay. */
    private fun shot(clip: String, seconds: Double, restY: Double?, zoom: Float = 1f): Shot {
        val descriptor = app.assets.openFd("SampleSigns/$clip.mp4")
        val frame = MediaMetadataRetriever().run {
            setDataSource(descriptor.fileDescriptor, descriptor.startOffset, descriptor.length)
            getFrameAtTime((seconds * 1e6).toLong(), MediaMetadataRetriever.OPTION_CLOSEST)!!.also { release() }
        }
        val height = (frame.height / zoom).toInt()
        val width = height * 3 / 4
        val centreX = (frame.width * 0.52f).toInt()
        val top = if (zoom == 1f) 0 else (frame.height * 0.02f).toInt()
        val picture = Bitmap.createBitmap(frame, centreX - width / 2, top, width, height).copy(Bitmap.Config.ARGB_8888, false)
        val overlay = HolisticLandmarkProvider(app, "holistic_landmarker.task").use { it.landmarks(BitmapFrame(picture, 1.0)).bodyOverlay(restY) }
        return Shot(picture, overlay)
    }

    private val watching by lazy { shot("rest", 0.5, restY = 0.86) }
    private val signing by lazy { shot("tomorrow_lifeprint", 1.0, restY = 0.86) }
    private val tooClose by lazy { shot("rest", 0.5, restY = null, zoom = 2.2f) }

    private fun recognition(shot: Shot) = CameraRecognition(FakeCamera(CameraPermission.GRANTED, shot.overlay, shot.picture.asImageBitmap()))

    private fun show(content: @Composable () -> Unit) {
        screen.value = null
        compose.waitForIdle()
        screen.value = content
    }

    private fun save(name: String) {
        compose.waitForIdle()
        Thread.sleep(300)
        val folder = File(app.getExternalFilesDir(null), "camera-screenshots").apply { mkdirs() }
        val bitmap = compose.onRoot().captureToImage().asAndroidBitmap()
        File(folder, "$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }

    /** Light and dark of what [content] shows. */
    private fun both(name: String, content: @Composable () -> Unit) {
        show(content)
        for (isDark in listOf(false, true)) {
            dark.value = isDark
            save("$name-${if (isDark) "dark" else "light"}")
        }
        dark.value = false
    }

    private fun call(fixture: DemoFixture, shot: Shot, state: CameraState? = null): ActiveCallViewModel {
        val model = runBlocking { withContext(Dispatchers.Main) { fixture.makeActiveCall(recognition(shot))!! } }
        state?.let { onMain { model.handle(RecognitionEvent.Camera(it)) } }
        return model
    }

    @Test
    fun classicCall() {
        if (!asked) return
        val signingCall = call(DemoFixture.SIGNING, signing)
        both("classic-signing") { ActiveCallScreen(signingCall, onLeave = {}, onShowNotes = null) }
        val watchingCall = call(DemoFixture.COMPOSING, watching, CameraState.WATCHING)
        both("classic-watching") { ActiveCallScreen(watchingCall, onLeave = {}, onShowNotes = null) }
        val cantSeeCall = call(DemoFixture.SIGNING, tooClose, CameraState.CANT_SEE)
        both("classic-cantsee") { ActiveCallScreen(cantSeeCall, onLeave = {}, onShowNotes = null) }
        val speakingCall = call(DemoFixture.SPEAKING, watching, CameraState.WATCHING)
        both("classic-speaking") { ActiveCallScreen(speakingCall, onLeave = {}, onShowNotes = null) }
        val candidateCall = call(DemoFixture.SIGNING, signing)
        onMain { candidateCall.handle(RecognitionEvent.Result(RecognitionResult.Candidate(Sign.TOMORROW))) }
        both("classic-candidate") { ActiveCallScreen(candidateCall, onLeave = {}, onShowNotes = null) }
    }

    @Test
    fun classicCallAtTheLargestFontScale() {
        if (!asked) return
        fontScale.value = 2f
        val signingCall = call(DemoFixture.SIGNING, signing)
        both("classic-signing-font2") { ActiveCallScreen(signingCall, onLeave = {}, onShowNotes = null) }
        val candidateCall = call(DemoFixture.SIGNING, signing)
        onMain { candidateCall.handle(RecognitionEvent.Result(RecognitionResult.Candidate(Sign.TOMORROW))) }
        both("classic-candidate-font2") { ActiveCallScreen(candidateCall, onLeave = {}, onShowNotes = null) }
        val speakingCall = call(DemoFixture.SPEAKING, watching, CameraState.WATCHING)
        both("classic-speaking-font2") { ActiveCallScreen(speakingCall, onLeave = {}, onShowNotes = null) }
    }

    @Test
    fun brief() {
        if (!asked) return
        val model = onMain { BriefModel(CallSetup.demo, RecordingDriver(), recognition(signing)) }
        onMain {
            model.handle(RecognitionEvent.Camera(CameraState.SIGNING))
            model.add(Sign.TOMORROW)
        }
        both("brief-signing") { BriefScreen(model, modeDescription = "Test mode", onApprove = {}, onBack = {}) }
    }

    @Test
    fun steer() {
        if (!asked) return
        val brief = Brief("b1", "Call on behalf of Riya.", "book a doctor's appointment", emptyList())
        val setup = CallSetup.demo.copy(delegation = Delegation(brief, attended = false, mode = CallMode.STEER), request = "Book a doctor's appointment")
        val driver = onMain { RecordingDriver() }
        val model = onMain { ActiveCallViewModel(setup, driver, recognition(signing)) }
        runBlocking { withContext(Dispatchers.Main) { model.start() } }
        onMain { driver.store.receive(ServerMessage.Status(CallState.IN_CALL)) }
        eventually { model.phase == ActiveCallViewModel.Phase.Live }
        show { SteerCallScreen(model, onLeave = {}, onShowNotes = {}) }
        compose.onNodeWithTag("steer.sign").performClick()
        compose.waitForIdle()
        onMain { model.handle(RecognitionEvent.Camera(CameraState.SIGNING)) }
        for (isDark in listOf(false, true)) {
            dark.value = isDark
            save("steer-signing-${if (isDark) "dark" else "light"}")
        }
    }
}
