package ai.ishara.demo.recognition.pipeline

import ai.ishara.demo.core.call.Sign
import ai.ishara.demo.recognition.CameraState
import ai.ishara.demo.recognition.Landmarks
import ai.ishara.demo.recognition.RecognitionEvent
import ai.ishara.demo.recognition.RecognitionResult
import ai.ishara.demo.recognition.RecognitionTestAssets
import ai.ishara.demo.recognition.RecognitionTestAssets.logits
import ai.ishara.demo.recognition.ScriptedFeed
import ai.ishara.demo.recognition.ScriptedLandmarkProvider
import ai.ishara.demo.recognition.core.NativeLogitsMatcher
import ai.ishara.demo.recognition.core.NativeRecognitionRules
import ai.ishara.demo.recognition.landmarks.LandmarkFrame
import ai.ishara.demo.recognition.landmarks.LogitsModel
import ai.ishara.demo.recognition.videoFrames
import androidx.test.ext.junit.runners.AndroidJUnit4
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.util.Collections

/**
 * ios/IsharaTests/PipelineRecognitionControllerTests' timing cases with the real detector and
 * matcher: the controller on the main thread, the pipeline on its worker.
 */
@RunWith(AndroidJUnit4::class)
class PipelineControllerNativeTest {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private val events: MutableList<RecognitionEvent> = Collections.synchronizedList(mutableListOf())

    @After
    fun tearDown() = scope.cancel()

    private fun results() = synchronized(events) { events.filterIsInstance<RecognitionEvent.Result>().map { it.result } }

    private suspend fun start(landmarks: List<LandmarkFrame>, extra: List<FeedItem> = emptyList()) = withContext(Dispatchers.Main) {
        val controller = PipelineRecognitionController(ScriptedFeed(videoFrames(landmarks) + extra), scope) {
            val rules = NativeRecognitionRules()
            val matcher = NativeLogitsMatcher(RecognitionTestAssets.bundleJson)
            PipelineComponents(
                ScriptedLandmarkProvider(landmarks),
                SegmentClassifier(LogitsModel { _, _ -> logits("hello", 0.9) }, matcher, rules),
                rules,
            ) { matcher.close() }
        }
        val flow = controller.signingEvents()
        scope.launch { flow.collect { events += it } }
        controller.start()
        controller
    }

    private suspend fun eventually(condition: () -> Boolean): Boolean =
        withTimeoutOrNull(5_000) {
            while (!condition()) delay(10)
            true
        } ?: false

    @Test
    fun acceptedSignBecomesAChip() = runBlocking {
        val controller = start(Landmarks.calibratedStream { Landmarks.sign(from = it) })

        assertTrue(eventually { results() == listOf(RecognitionResult.Recognised(Sign.HELLO)) })
        assertTrue("checklist and calibration came from the frames", controller.getReady.state.value.isReady)
        assertTrue(events.contains(RecognitionEvent.Camera(CameraState.SIGNING)))
    }

    private val shortRest = Landmarks.calibratedStream { start ->
        Landmarks.run(start, 0.8, wristY = Landmarks.SIGNING_Y) + Landmarks.run(start + 0.8, 0.1)
    }

    @Test
    fun holdAfterAReplayedClipLetsTheSignFinish() = runBlocking {
        start(shortRest, extra = listOf(FeedItem.Hold(ClipFeed.HOLD_AFTER_CLIP)))

        assertTrue(eventually { results() == listOf(RecognitionResult.Recognised(Sign.HELLO)) })
    }

    @Test
    fun withoutTheHoldAClipEndingTooSoonStaysOpen() = runBlocking {
        start(shortRest)

        assertTrue(eventually { events.lastOrNull() == RecognitionEvent.Camera(CameraState.SIGNING) })
        delay(300)
        assertEquals(emptyList<RecognitionResult>(), results())
    }
}
