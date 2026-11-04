package ai.ishara.demo.recognition.pipeline

import ai.ishara.demo.core.call.Sign
import ai.ishara.demo.recognition.BodyOverlay
import ai.ishara.demo.recognition.CameraPermission
import ai.ishara.demo.recognition.CameraState
import ai.ishara.demo.recognition.Landmarks
import ai.ishara.demo.recognition.RecognitionEvent
import ai.ishara.demo.recognition.RecognitionResult
import ai.ishara.demo.recognition.ScriptedFeed
import ai.ishara.demo.recognition.ScriptedLandmarkProvider
import ai.ishara.demo.recognition.ScriptedRules
import ai.ishara.demo.recognition.ScriptedRules.Companion.cut
import ai.ishara.demo.recognition.ScriptedRules.Companion.ms
import ai.ishara.demo.recognition.ScriptedRules.Companion.status
import ai.ishara.demo.recognition.TimedFrame
import ai.ishara.demo.recognition.core.DetectorEvent
import ai.ishara.demo.recognition.core.LogitsMatch
import ai.ishara.demo.recognition.core.LogitsMatching
import ai.ishara.demo.recognition.landmarks.LandmarkFrame
import ai.ishara.demo.recognition.landmarks.LogitsModel
import ai.ishara.demo.recognition.videoFrames
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The controller with scripted feed, landmarks and RecognitionCore rules: frames → checklist and
 * calibration → detector → classifier → events for the call screen. Mirrors
 * ios/IsharaTests/PipelineRecognitionControllerTests; PipelineControllerNativeTest repeats the
 * timing-sensitive cases with the real detector on the device.
 */
class PipelineRecognitionControllerTest {
    private val stream = Landmarks.calibratedStream { Landmarks.sign(from = it) }

    /** The real detector's events for [stream]: watching after calibration, a sign cut 0.4 s into the rest. */
    private val signEvents = mapOf(
        ms(stream[61].timestamp) to listOf(status(CameraState.WATCHING)),
        ms(stream[81].timestamp) to listOf(status(CameraState.SIGNING)),
        ms(stream[114].timestamp) to listOf(cut(stream[72].timestamp, stream[102].timestamp), status(CameraState.WATCHING)),
    )

    private class FakeCamera : FeedCamera {
        override val permission = MutableStateFlow(CameraPermission.GRANTED)
        override val isUnavailable = MutableStateFlow(false)
        override val overlay = MutableStateFlow<BodyOverlay?>(null)

        override fun onPermissionResult(granted: Boolean) = Unit

        @Composable
        override fun Preview(modifier: Modifier) = Unit
    }

    private fun TestScope.controller(
        landmarks: List<LandmarkFrame> = stream,
        extra: List<FeedItem> = emptyList(),
        events: Map<Long, List<DetectorEvent>> = signEvents,
        match: LogitsMatch? = LogitsMatch.Chip("hello", 0.9, 0.8, emptyList()),
        feed: FrameFeed = ScriptedFeed(videoFrames(landmarks) + extra),
    ): PipelineRecognitionController {
        val rules = ScriptedRules(events = events)
        return PipelineRecognitionController(feed, this, workerDispatcher = StandardTestDispatcher(testScheduler), log = {}) {
            PipelineComponents(
                ScriptedLandmarkProvider(landmarks),
                SegmentClassifier(LogitsModel { _, _ -> FloatArray(250) }, match?.let { result -> LogitsMatching { _, _ -> result } }, rules) {},
                rules,
            )
        }
    }

    private fun TestScope.collect(controller: PipelineRecognitionController): MutableList<RecognitionEvent> {
        val events = mutableListOf<RecognitionEvent>()
        val flow = controller.signingEvents()
        backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) { flow.collect { events += it } }
        return events
    }

    private fun results(events: List<RecognitionEvent>) = events.filterIsInstance<RecognitionEvent.Result>().map { it.result }

    @Test
    fun acceptedSignBecomesAChip() = runTest {
        val controller = controller()
        val events = collect(controller)

        controller.start()
        advanceUntilIdle()

        assertEquals(listOf(RecognitionResult.Recognised(Sign.HELLO)), results(events))
        assertTrue("checklist and calibration came from the frames", controller.getReady.state.value.isReady)
        assertEquals(
            listOf(CameraState.WATCHING, CameraState.SIGNING, CameraState.WATCHING),
            events.filterIsInstance<RecognitionEvent.Camera>().map { it.state },
        )
    }

    @Test
    fun withoutAMatcherEverySignIsAQuestionMark() = runTest {
        val controller = controller(match = null)
        val events = collect(controller)

        controller.start()
        advanceUntilIdle()

        assertEquals(listOf(RecognitionResult.Unsure), results(events))
    }

    @Test
    fun rejectedAttemptProducesNothing() = runTest {
        val lost = Landmarks.calibratedStream { Landmarks.lostMidSign(from = it) }
        val controller = controller(
            landmarks = lost,
            events = mapOf(ms(lost[100].timestamp) to listOf(cut(lost[72].timestamp, lost[100].timestamp, "lost_tracking"), status(CameraState.CANT_SEE))),
        )
        val events = collect(controller)

        controller.start()
        advanceUntilIdle()

        assertEquals(listOf(RecognitionEvent.Camera(CameraState.CANT_SEE)), events)
    }

    /** A replayed clip that ends 0.1 s after the hands come down; the detector ends a sign 0.4 s into rest. */
    private val shortRest = Landmarks.calibratedStream { start ->
        Landmarks.run(start, 0.8, wristY = Landmarks.SIGNING_Y) + Landmarks.run(start + 0.8, 0.1)
    }
    private val endsInHeldFrames = mapOf(
        ms(shortRest.last().timestamp + 9 / 30.0) to listOf(cut(shortRest[72].timestamp, shortRest[102].timestamp), status(CameraState.WATCHING)),
    )

    @Test
    fun holdAfterAReplayedClipLetsTheSignFinish() = runTest {
        val controller = controller(landmarks = shortRest, extra = listOf(FeedItem.Hold(0.8)), events = endsInHeldFrames)
        val events = collect(controller)

        controller.start()
        advanceUntilIdle()

        assertEquals(listOf(RecognitionResult.Recognised(Sign.HELLO)), results(events))
    }

    @Test
    fun withoutTheHoldAClipEndingTooSoonStaysOpen() = runTest {
        val controller = controller(landmarks = shortRest, events = endsInHeldFrames)
        val events = collect(controller)

        controller.start()
        advanceUntilIdle()

        assertEquals(emptyList<RecognitionResult>(), results(events))
    }

    @Test
    fun previewShowsTheLatestTrackedBodyAndTheRestLine() = runTest {
        val camera = FakeCamera()
        val controller = controller(feed = ScriptedFeed(videoFrames(stream), camera))
        collect(controller)

        controller.start()
        advanceUntilIdle()

        val overlay = checkNotNull(camera.overlay.value)
        assertEquals(720, overlay.imageWidth)
        assertEquals(1280, overlay.imageHeight)
        assertEquals("the last frame has both hands back at rest", listOf(Landmarks.REST_Y, Landmarks.REST_Y), overlay.wrists.map { it.y })
        assertEquals(2, overlay.shoulders.size)
        assertEquals("calibration finished, so the rest line is known", Landmarks.CALIBRATED_REST_Y, overlay.restY!!, 0.0)
        assertTrue(controller.camera === camera)
    }

    @Test
    fun oneOverlayPerTrackedFrameNoneForHeldOrSkippedFrames() = runTest {
        val landmarks = Landmarks.calibratedStream { emptyList() }
        val items = Channel<FeedItem>(Channel.UNLIMITED)
        videoFrames(landmarks).forEach { items.trySend(it) }
        items.trySend(FeedItem.Frame(TimedFrame(99.0))) // no landmarks: skipped
        items.trySend(FeedItem.Hold(0.1))
        items.close()
        val rules = ScriptedRules()
        val components = PipelineComponents(ScriptedLandmarkProvider(landmarks), SegmentClassifier(null, null, rules) {}, rules)
        val overlays = mutableListOf<BodyOverlay>()

        PipelineRecognitionController.process(items, components, log = {}) { output ->
            if (output is PipelineRecognitionController.WorkerOutput.Overlay) overlays += output.overlay
        }

        assertEquals(landmarks.size, overlays.size)
        assertNull(overlays.first().restY)
        assertNotNull(overlays.last().restY)
        assertEquals("held frames still reach the detector", landmarks.size - 61 + 3, rules.detectorFrames.size)
    }

    @Test
    fun heldFramesRepeatTheLastFrameAt30fps() {
        val held = PipelineRecognitionController.held(Landmarks.frame(t = 1.0), 0.1)

        assertEquals(listOf(1033L, 1067L, 1100L), held.map { ms(it.timestamp) })
        assertEquals(24, PipelineRecognitionController.held(Landmarks.frame(t = 1.0), ClipFeed.HOLD_AFTER_CLIP).size)
        assertTrue(held.all { it.leftHand == Landmarks.frame(t = 1.0).leftHand })
    }

    @Test
    fun setupFailureIsReported() = runTest {
        val controller = PipelineRecognitionController(ScriptedFeed(emptyList()), this, workerDispatcher = StandardTestDispatcher(testScheduler), log = {}) {
            throw IllegalStateException("holistic_landmarker.task is missing")
        }

        controller.start()
        advanceUntilIdle()

        assertEquals("Recognition can't start: holistic_landmarker.task is missing", controller.failure.value)
    }

    @Test
    fun feedFailureIsReported() = runTest {
        val feed = ScriptedFeed(emptyList())
        val controller = controller(feed = feed)

        feed.onFailure!!.invoke(IllegalStateException("This device has no usable front camera."))
        advanceUntilIdle()

        assertEquals("Recognition can't start: This device has no usable front camera.", controller.failure.value)
    }

    @Test
    fun aNewCallScreenStreamFinishesTheOldOne() = runTest {
        val controller = controller()
        val first = controller.signingEvents()
        controller.signingEvents()

        assertEquals(emptyList<RecognitionEvent>(), first.toList())
    }

    @Test
    fun resultsReachOnlyTheNewestStream() = runTest {
        val controller = controller()
        val old = collect(controller)
        val current = collect(controller)

        controller.start()
        advanceUntilIdle()

        assertEquals(emptyList<RecognitionEvent>(), old)
        assertEquals(listOf(RecognitionResult.Recognised(Sign.HELLO)), results(current))
    }

    @Test
    fun stopEndsFramesAndTheStream() = runTest {
        val feed = ScriptedFeed(emptyList())
        val controller = controller(feed = feed)
        val events = controller.signingEvents()

        controller.stop()

        assertEquals(emptyList<RecognitionEvent>(), events.toList())
        assertEquals(1, feed.stopCount)
    }

    @Test
    fun replayGoesToTheFeed() = runTest {
        val feed = ScriptedFeed(emptyList()).apply { replayOptions = listOf("hello_01") }
        val controller = controller(feed = feed)

        controller.replay("hello_01")

        assertEquals(listOf("hello_01"), controller.replayOptions)
        assertEquals(listOf("hello_01"), feed.replayed)
        assertNull("saved videos have no live camera", controller.camera)
    }
}
