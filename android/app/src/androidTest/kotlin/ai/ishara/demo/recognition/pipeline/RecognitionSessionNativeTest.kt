package ai.ishara.demo.recognition.pipeline

import ai.ishara.demo.recognition.CameraState
import ai.ishara.demo.recognition.GetReadyModel.Check
import ai.ishara.demo.recognition.Landmarks
import ai.ishara.demo.recognition.core.CalibrationError
import ai.ishara.demo.recognition.core.NativeRecognitionRules
import ai.ishara.demo.recognition.landmarks.LandmarkFrame
import ai.ishara.demo.recognition.pipeline.RecognitionSession.Output
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import kotlin.math.roundToLong

/** ios/IsharaTests/RecognitionSessionTests.swift against the real RecognitionCore detector. */
@RunWith(AndroidJUnit4::class)
class RecognitionSessionNativeTest {
    private fun run(frames: List<LandmarkFrame>): Pair<RecognitionSession, List<Output>> {
        val session = RecognitionSession(NativeRecognitionRules())
        return session to frames.flatMap(session::process)
    }

    private fun clips(outputs: List<Output>) = outputs.filterIsInstance<Output.Sign>().map { it.clip }

    private fun cameraStates(outputs: List<Output>) = outputs.filterIsInstance<Output.Camera>().map { it.state }

    @Test
    fun calibratesTwoSecondsAfterTheChecklistPasses() {
        val (session, outputs) = run(Landmarks.run(from = 0.0, seconds = 2.1))

        assertEquals(listOf(Output.Passed(Check.BOTH_HANDS), Output.Passed(Check.FACE), Output.Passed(Check.LIGHT)), outputs.take(3))
        assertTrue(outputs.contains(Output.Calibrating(1.0)))
        val restY = outputs.filterIsInstance<Output.Calibrated>().first().restY
        assertEquals("median wrist height minus the 0.08 margin", 0.82, restY, 1e-6)
        assertEquals(restY, session.restY!!, 0.0)
    }

    @Test
    fun noSignsAreCutBeforeCalibrationEnds() {
        val (session, outputs) = run(Landmarks.sign(from = 0.0) + Landmarks.sign(from = 1.4))

        assertNotNull(session.restY)
        assertEquals(0, clips(outputs).size)
        assertFalse(cameraStates(outputs).contains(CameraState.SIGNING))
    }

    @Test
    fun calibrationStartsOverWhenTheUserCantBeSeen() {
        val (session, outputs) = run(listOf(Landmarks.frame(t = 0.0)) + Landmarks.run(from = 1.0 / 30, seconds = 2.1, body = false))

        assertTrue(outputs.contains(Output.CalibrationRestarted(CalibrationError.CANT_SEE)))
        assertFalse(outputs.any { it is Output.Calibrated })
        assertNull(session.restY)
    }

    @Test
    fun acceptedSignHandsBackItsFramesWithPreRoll() {
        val (_, outputs) = run(Landmarks.calibratedStream { Landmarks.sign(from = it) })

        val clip = clips(outputs).single().frames
        assertEquals("0.2 s pre-roll", 2.4, clip.first().timestamp, 0.02)
        assertEquals("ends when the hands rest", 3.4, clip.last().timestamp, 0.02)
        assertEquals(listOf(CameraState.WATCHING, CameraState.SIGNING, CameraState.WATCHING), cameraStates(outputs))
    }

    @Test
    fun acceptedSignCarriesTheCalibratedRestLine() {
        val (session, outputs) = run(Landmarks.calibratedStream { Landmarks.sign(from = it) })

        val clip = clips(outputs).single()
        assertEquals(session.restY!!, clip.restY, 0.0)
        assertEquals(Landmarks.CALIBRATED_REST_Y, clip.restY, 1e-6)
    }

    @Test
    fun acceptedSignAlsoHandsBackTheRestThatEndedIt() {
        val (_, outputs) = run(Landmarks.calibratedStream { Landmarks.sign(from = it) })

        val clip = clips(outputs).single()
        val end = clip.frames.last().timestamp
        assertTrue("no frame twice", clip.restAfter.all { it.timestamp > end })
        assertEquals("starts right after the cut", end + 1.0 / 30, clip.restAfter.first().timestamp, 1e-6)
        assertEquals("up to the frame that ended the sign, 0.4 s of rest later", 0.4, clip.restAfter.last().timestamp - end, 0.02)
        assertTrue(clip.restAfter.all { it.leftHand?.first()?.y == Landmarks.REST_Y })
    }

    @Test
    fun rejectedAttemptGivesNothingToMatch() {
        val (_, outputs) = run(Landmarks.calibratedStream { Landmarks.lostMidSign(from = it) })

        assertEquals(0, clips(outputs).size)
        assertEquals(listOf(CameraState.WATCHING, CameraState.SIGNING, CameraState.CANT_SEE, CameraState.WATCHING), cameraStates(outputs))
    }

    @Test
    fun detectorFrameCarriesBodyAndBothWrists() {
        val frame = RecognitionSession.detectorFrame(Landmarks.frame(t = 1.5, wristY = 0.7f))

        assertEquals(1.5, frame.t, 0.0)
        assertTrue(frame.body)
        assertEquals(listOf(700L, 700L), frame.wrists.map { (it.y * 1000).roundToLong() })
    }
}
