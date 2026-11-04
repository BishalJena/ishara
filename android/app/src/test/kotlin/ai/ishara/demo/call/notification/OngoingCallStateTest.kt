package ai.ishara.demo.call.notification

import ai.ishara.demo.call.ActiveCallViewModel.EndReason
import ai.ishara.demo.call.ActiveCallViewModel.Phase
import ai.ishara.demo.call.notification.OngoingCallState.Driving
import ai.ishara.demo.core.call.CallState
import ai.ishara.demo.core.call.Caption
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** The notification follows the call like iOS `CallActivityController.update(from:)` and the Live Activity's texts. */
class OngoingCallStateTest {
    private val receptionist = Caption("We have 4 pm tomorrow. Does that work?", 10.0, Caption.Speaker.RECEPTIONIST)
    private val agent = Caption("One moment, please.", 11.0, Caption.Speaker.AGENT)

    private fun state(phase: Phase, captions: List<Caption> = emptyList(), steppingIn: Boolean = false, connectedAt: Double? = null) =
        OngoingCallState.of("City Clinic", phase, captions, steppingIn, connectedAt)

    @Test
    fun aPlacedCallSaysItIsCalling() {
        val starting = OngoingCallState.starting("City Clinic")

        assertEquals("Calling City Clinic…", starting.latestLine)
        assertEquals(Driving.CONNECTING, starting.driving)
        assertEquals("Calling…", starting.status)
        assertNull(starting.timerStart)
        assertEquals(starting, state(Phase.Connecting(CallState.RINGING)))
    }

    @Test
    fun isharaIsAnsweringUntilTheUserStepsIn() {
        val handled = state(Phase.Live, listOf(receptionist), connectedAt = 5.0)
        assertEquals(Driving.AGENT, handled.driving)
        assertEquals("Answering for you", handled.status)
        assertEquals("Ishara is on the call", handled.headline)

        val steppedIn = state(Phase.Live, listOf(receptionist), steppingIn = true, connectedAt = 5.0)
        assertEquals(Driving.USER, steppedIn.driving)
        assertEquals("You're replying", steppedIn.status)
    }

    @Test
    fun theLatestLineIsQuotedWithWhoSaidIt() {
        val theirs = state(Phase.Live, listOf(agent, receptionist), connectedAt = 5.0)
        assertEquals("\u201CWe have 4 pm tomorrow. Does that work?\u201D", theirs.quotedLine)
        assertFalse(theirs.latestSpeakerIsUs)

        val ours = state(Phase.Live, listOf(receptionist, agent), connectedAt = 5.0)
        assertEquals("One moment, please.", ours.latestLine)
        assertTrue(ours.latestSpeakerIsUs)
    }

    @Test
    fun connectedWithNothingSaidYet() {
        assertEquals("Connected", state(Phase.Live, connectedAt = 5.0).latestLine)
    }

    @Test
    fun theTimerRunsFromConnectionUntilTheEnd() {
        assertEquals(5.0, state(Phase.Live, connectedAt = 5.0).timerStart!!, 0.0)
        val ended = state(Phase.Ended(EndReason.RemoteEnded), listOf(receptionist), connectedAt = 5.0)
        assertNull("an ended call's timer stops", ended.timerStart)
        assertEquals("Call ended", ended.headline)
        assertEquals("Call ended · open Ishara for the gist", ended.status)
    }

    @Test
    fun aDroppedConnectionIsStillTheSameDriver() {
        assertEquals(Driving.AGENT, state(Phase.Interrupted("Nothing will be sent"), connectedAt = 5.0).driving)
        assertEquals(Driving.USER, state(Phase.Disconnected("gone"), steppingIn = true, connectedAt = 5.0).driving)
        assertEquals(Driving.ENDED, state(Phase.Ended(EndReason.Failed("no"))).driving)
    }
}
