package ai.ishara.demo.recognition

import ai.ishara.demo.core.call.Sign
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** The scripted recognizer from ios/IsharaTests/FakeCallTests.swift, on virtual time. */
@OptIn(ExperimentalCoroutinesApi::class)
class ScriptedRecognitionTest {
    private fun TestScope.recognizer(script: List<RecognitionResult> = emptyList(), offersReplay: Boolean = false) =
        ScriptedRecognitionController(script, offersReplay, timeScale = 1.0, scope = backgroundScope)

    private fun TestScope.record(recognition: ScriptedRecognitionController): MutableList<RecognitionEvent> {
        val events = mutableListOf<RecognitionEvent>()
        val stream = recognition.signingEvents()
        backgroundScope.launch { stream.collect { events += it } }
        return events
    }

    /** Background coroutines (the recognizer's timers) aren't run by `advanceUntilIdle`. */
    private fun TestScope.settle() {
        testScheduler.advanceTimeBy(60_000)
        testScheduler.runCurrent()
    }

    @Test
    fun replayedSignShowsTheYellowPillThenTheResultThenGreen() = runTest {
        val recognition = recognizer(offersReplay = true)
        val events = record(recognition)

        recognition.replay("hello")
        recognition.replay(RecognitionResult.UNSURE_OPTION)
        settle()

        val signing = RecognitionEvent.Camera(CameraState.SIGNING)
        val watching = RecognitionEvent.Camera(CameraState.WATCHING)
        assertEquals(
            listOf(
                signing, signing,
                RecognitionEvent.Result(RecognitionResult.Recognised(Sign.HELLO)), watching,
                RecognitionEvent.Result(RecognitionResult.Unsure), watching,
            ),
            events,
        )
        assertEquals(
            "every sign, ?, frame, and a candidate per rehearsed sign",
            Sign.entries.size + 2 + Sign.rehearsed.size,
            recognition.replayOptions.size,
        )
        assertEquals(listOf("?", "frame"), recognition.replayOptions.take(2))
    }

    @Test
    fun theResultComesAboutASecondAfterThePill() = runTest {
        val recognition = recognizer()
        val events = record(recognition)

        recognition.sign(RecognitionResult.Recognised(Sign.YES))
        testScheduler.advanceTimeBy(1_100)
        testScheduler.runCurrent()
        assertEquals(listOf<RecognitionEvent>(RecognitionEvent.Camera(CameraState.SIGNING)), events)

        testScheduler.advanceTimeBy(200)
        testScheduler.runCurrent()
        assertEquals(RecognitionEvent.Result(RecognitionResult.Recognised(Sign.YES)), events[1])
    }

    @Test
    fun replayMenuOffersCandidatesAndTheFramingCase() = runTest {
        val recognition = recognizer(offersReplay = true)
        val events = record(recognition)

        recognition.replay("tomorrow?")
        recognition.replay(RecognitionResult.FRAMING_OPTION)
        recognition.replay("banana")
        settle()

        val results = events.filterIsInstance<RecognitionEvent.Result>().map { it.result }
        assertEquals(listOf(RecognitionResult.Candidate(Sign.TOMORROW), RecognitionResult.HandLeftFrame), results)
        assertTrue("tomorrow?" in recognition.replayOptions)
    }

    @Test
    fun scriptPlaysOnceSigningStarts() = runTest {
        val recognition = recognizer(script = listOf(RecognitionResult.Recognised(Sign.YES), RecognitionResult.Unsure))
        val events = record(recognition)
        settle()

        assertEquals(
            listOf(RecognitionResult.Recognised(Sign.YES), RecognitionResult.Unsure),
            events.filterIsInstance<RecognitionEvent.Result>().map { it.result },
        )
    }

    @Test
    fun aNewStreamFinishesTheOldOneSoNoResultReachesAnOlderScreen() = runTest {
        val recognition = recognizer()
        val old = record(recognition)
        val current = record(recognition)

        recognition.replay("yes")
        settle()

        assertTrue(old.isEmpty())
        assertEquals(3, current.size)
    }

    @Test
    fun stopCancelsWhatIsStillToCome() = runTest {
        val recognition = recognizer()
        val events = record(recognition)

        recognition.sign(RecognitionResult.Recognised(Sign.YES))
        recognition.stop()
        settle()

        assertEquals(listOf<RecognitionEvent>(RecognitionEvent.Camera(CameraState.SIGNING)), events)
    }

    @Test
    fun getReadyTicksOnTimersWhenReplayingFixedResults() = runTest {
        val recognition = recognizer()
        assertTrue(recognition.replayOptions.isEmpty())

        recognition.start()
        testScheduler.advanceTimeBy(1_900)
        testScheduler.runCurrent()
        assertTrue(recognition.getReady.state.value.allChecksPassed)
        assertFalse("calibration takes 2 s more", recognition.getReady.state.value.isReady)

        settle()
        assertTrue(recognition.getReady.state.value.isReady)
    }
}
