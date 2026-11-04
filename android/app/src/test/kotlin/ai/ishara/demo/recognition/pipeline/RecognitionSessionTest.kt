package ai.ishara.demo.recognition.pipeline

import ai.ishara.demo.recognition.CameraState
import ai.ishara.demo.recognition.GetReadyModel.Check
import ai.ishara.demo.recognition.Landmarks
import ai.ishara.demo.recognition.ScriptedRules
import ai.ishara.demo.recognition.ScriptedRules.Companion.cut
import ai.ishara.demo.recognition.ScriptedRules.Companion.ms
import ai.ishara.demo.recognition.ScriptedRules.Companion.status
import ai.ishara.demo.recognition.specParams
import ai.ishara.demo.recognition.core.CalibrationError
import ai.ishara.demo.recognition.core.DetectorPoint
import ai.ishara.demo.recognition.landmarks.LandmarkFrame
import ai.ishara.demo.recognition.pipeline.RecognitionSession.Output
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The session's own logic (checklist, calibration window, segment slicing) with scripted
 * RecognitionCore rules. RecognitionSessionNativeTest runs ios/IsharaTests/RecognitionSessionTests
 * against the real detector on the device.
 */
class RecognitionSessionTest {
    private fun run(rules: ScriptedRules, frames: List<LandmarkFrame>): Pair<RecognitionSession, List<Output>> {
        val session = RecognitionSession(rules)
        return session to frames.flatMap(session::process)
    }

    private fun clips(outputs: List<Output>) = outputs.filterIsInstance<Output.Sign>().map { it.clip }

    private fun cameraStates(outputs: List<Output>) = outputs.filterIsInstance<Output.Camera>().map { it.state }

    @Test
    fun checklistComesFromWhatTheTrackerSees() {
        assertEquals(setOf(Check.FACE, Check.BOTH_HANDS, Check.LIGHT), RecognitionSession.checks(Landmarks.frame(t = 0.0)))
        assertEquals(setOf(Check.FACE, Check.LIGHT), RecognitionSession.checks(Landmarks.frame(t = 0.0, hands = false)))
        assertEquals("one hand isn't both hands", setOf(Check.FACE, Check.LIGHT), RecognitionSession.checks(Landmarks.frame(t = 0.0, rightHand = false)))
        assertEquals(setOf(Check.FACE, Check.BOTH_HANDS), RecognitionSession.checks(Landmarks.frame(t = 0.0, body = false)))
        assertEquals(emptySet<Check>(), RecognitionSession.checks(LandmarkFrame.create(0.0, Landmarks.size)))
    }

    @Test
    fun checksPassOnceEachAsTheyAreSeen() {
        val frames = listOf(Landmarks.frame(t = 0.0, hands = false), Landmarks.frame(t = 0.1, hands = false), Landmarks.frame(t = 0.2))

        val (_, outputs) = run(ScriptedRules(), frames)

        assertEquals(listOf(Output.Passed(Check.FACE), Output.Passed(Check.LIGHT), Output.Passed(Check.BOTH_HANDS)), outputs)
    }

    @Test
    fun calibratesTwoSecondsAfterTheChecklistPasses() {
        val rules = ScriptedRules(restY = 0.77)

        val (session, outputs) = run(rules, Landmarks.run(from = 0.0, seconds = 2.1))

        assertEquals(listOf(Output.Passed(Check.BOTH_HANDS), Output.Passed(Check.FACE), Output.Passed(Check.LIGHT)), outputs.take(3))
        assertTrue(outputs.contains(Output.Calibrating(1.0)))
        assertEquals(1, outputs.count { it is Output.Calibrated })
        assertTrue(outputs.contains(Output.Calibrated(0.77)))
        assertEquals(0.77, session.restY!!, 0.0)
        val recording = rules.calibrations.single()
        assertEquals("the recording starts at the frame that passed the checklist", 0.0, recording.first().t, 0.0)
        assertEquals(2.0, recording.last().t, 1e-9)
        assertEquals(61, recording.size)
    }

    @Test
    fun calibrationStartsOverWhenTheRecordingCantBeUsed() {
        val rules = ScriptedRules(calibrationErrors = ArrayDeque(listOf(CalibrationError.CANT_SEE)))

        val (session, outputs) = run(rules, Landmarks.run(from = 0.0, seconds = 4.2))

        assertTrue(outputs.contains(Output.CalibrationRestarted(CalibrationError.CANT_SEE)))
        assertEquals(2, rules.calibrations.size)
        assertEquals("the retry records from the frame that failed", 2.0, rules.calibrations[1].first().t, 1e-9)
        assertEquals(4.0, rules.calibrations[1].last().t, 1e-9)
        assertEquals(Landmarks.CALIBRATED_REST_Y, session.restY!!, 0.0)
    }

    @Test
    fun noRestLineOrDetectorBeforeCalibrationEnds() {
        val rules = ScriptedRules(events = mapOf(ms(1.0) to listOf(status(CameraState.SIGNING))))

        val (session, outputs) = run(rules, Landmarks.run(from = 0.0, seconds = 1.9))

        assertNull(session.restY)
        assertTrue(rules.detectorFrames.isEmpty())
        assertTrue(cameraStates(outputs).isEmpty())
    }

    @Test
    fun acceptedSignHandsBackItsFramesTheRestAfterItAndTheRestLine() {
        val stream = Landmarks.calibratedStream { Landmarks.sign(from = it) }
        // The detector reports frame times: a start with 0.2 s pre-roll, the first rest frame as
        // the end, and the cut 0.4 s of rest later.
        val (start, end, endedAt) = listOf(72, 102, 114).map { stream[it].timestamp }
        val rules = ScriptedRules(
            events = mapOf(
                ms(stream[62].timestamp) to listOf(status(CameraState.WATCHING)),
                ms(stream[81].timestamp) to listOf(status(CameraState.SIGNING)),
                ms(endedAt) to listOf(cut(start, end), status(CameraState.WATCHING)),
            ),
        )

        val (_, outputs) = run(rules, stream)

        val clip = clips(outputs).single()
        assertEquals(stream.subList(72, 103), clip.frames)
        assertEquals("from right after the cut up to the frame that ended the sign", stream.subList(103, 115), clip.restAfter)
        assertEquals(Landmarks.CALIBRATED_REST_Y, clip.restY, 0.0)
        assertEquals(listOf(CameraState.WATCHING, CameraState.SIGNING, CameraState.WATCHING), cameraStates(outputs))
    }

    @Test
    fun rejectedAttemptGivesNothingToMatch() {
        val rules = ScriptedRules(events = mapOf(ms(3.8) to listOf(cut(2.4, 3.8, reason = "lost_tracking"), status(CameraState.CANT_SEE))))

        val (_, outputs) = run(rules, Landmarks.calibratedStream { Landmarks.lostMidSign(from = it) })

        assertTrue(clips(outputs).isEmpty())
        assertEquals(listOf(CameraState.CANT_SEE), cameraStates(outputs))
    }

    @Test
    fun recentFramesCoverOnlyTheLongestSignPlusPreRollAndEndRest() {
        val rules = ScriptedRules(events = mapOf(ms(10.0) to listOf(cut(3.0, 10.0))))

        val (_, outputs) = run(rules, Landmarks.run(from = 0.0, seconds = 10.1))

        val horizon = specParams.maxSignS + specParams.preRollS + specParams.endRestS + 1
        assertEquals(10.0 - horizon, clips(outputs).single().frames.first().timestamp, 1.0 / 30)
    }

    @Test
    fun detectorFrameCarriesBodyAndBothWrists() {
        val frame = RecognitionSession.detectorFrame(Landmarks.frame(t = 1.5, wristY = 0.7f))

        assertEquals(1.5, frame.t, 0.0)
        assertTrue(frame.body)
        assertEquals(listOf(DetectorPoint(0.6f.toDouble(), 0.7f.toDouble()), DetectorPoint(0.4f.toDouble(), 0.7f.toDouble())), frame.wrists)
        assertFalse(RecognitionSession.detectorFrame(Landmarks.frame(t = 0.0, body = false)).body)
        assertEquals(emptyList<DetectorPoint>(), RecognitionSession.detectorFrame(Landmarks.frame(t = 0.0, hands = false)).wrists)
    }

    @Test
    fun closingFreesTheDetector() {
        val rules = ScriptedRules()
        val (session, _) = run(rules, Landmarks.run(from = 0.0, seconds = 2.1))

        session.close()

        assertEquals(1, rules.closedDetectors)
        assertNull(session.restY)
    }
}
