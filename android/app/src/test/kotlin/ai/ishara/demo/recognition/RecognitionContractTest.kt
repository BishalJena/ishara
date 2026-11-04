package ai.ishara.demo.recognition

import ai.ishara.demo.core.call.CoreJson
import ai.ishara.demo.core.call.Sign
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.encodeToString
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Mirrors ios/IsharaTests/GetReadyModelTests.swift and the replay spellings in RecognitionController.swift. */
class RecognitionContractTest {
    @Test
    fun everySignWireNameIsItsSerialName() {
        for (sign in Sign.entries) {
            assertEquals("\"${sign.wire}\"", CoreJson.encodeToString(sign))
            assertEquals(sign, Sign.fromWire(sign.wire))
        }
        assertNull(Sign.fromWire("HELLO"))
    }

    @Test
    fun replaySpellings() {
        assertEquals(RecognitionResult.Recognised(Sign.TOMORROW), RecognitionResult.fromReplayOption(" Tomorrow "))
        assertEquals(RecognitionResult.Candidate(Sign.WAIT), RecognitionResult.fromReplayOption("wait?"))
        assertEquals(RecognitionResult.Unsure, RecognitionResult.fromReplayOption("?"))
        assertEquals(RecognitionResult.HandLeftFrame, RecognitionResult.fromReplayOption("frame"))
        assertNull(RecognitionResult.fromReplayOption("banana"))
        assertNull(RecognitionResult.fromReplayOption("banana?"))
    }

    @Test
    fun calibrationNeedsEveryCheckFirst() {
        val model = GetReadyModel()
        model.recordCalibration(1.0)
        assertEquals(0.0, model.state.value.secondsAtRest, 0.0)
        GetReadyModel.Check.entries.dropLast(1).forEach(model::pass)
        model.recordCalibration(1.0)
        assertEquals(0.0, model.state.value.secondsAtRest, 0.0)
        model.pass(GetReadyModel.Check.entries.last())
        model.recordCalibration(1.0)
        assertEquals(0.5, model.state.value.calibrationProgress, 1e-9)
        assertFalse(model.state.value.isReady)
    }

    @Test
    fun calibrationIsClampedAndRestartable() {
        val model = GetReadyModel()
        GetReadyModel.Check.entries.forEach(model::pass)
        model.recordCalibration(5.0)
        assertEquals(GetReadyModel.CALIBRATION_SECONDS, model.state.value.secondsAtRest, 0.0)
        assertTrue(model.state.value.isReady)
        model.restartCalibration()
        assertFalse(model.state.value.isCalibrated)
        model.recordCalibration(-1.0)
        assertEquals(0.0, model.state.value.secondsAtRest, 0.0)
    }

    @Test
    fun twentyTimerStepsOfATenthCalibrate() {
        val model = GetReadyModel()
        GetReadyModel.Check.entries.forEach(model::pass)
        repeat(20) { model.advanceCalibration(0.1) }
        assertTrue(model.state.value.isCalibrated)
    }

    @Test
    fun simulatedChecksEndReady() = runTest {
        val model = GetReadyModel()
        model.runSimulatedChecks(timeScale = 0.01)
        assertTrue(model.state.value.isReady)
    }
}
