package ai.ishara.demo.ui.classic

import ai.ishara.demo.ui.classic.Turns.TURN1
import ai.ishara.demo.ui.classic.Turns.TURN3
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The call screen's layout rules at the default and the largest font scale (Android's Dynamic
 * Type), on the debug fixtures: the sentence SEND or STOP acts on is wholly readable right
 * above its button, the signing video is never dropped, and the controls that matter stay on
 * screen. Mirrors iOS
 * `testSentenceStaysBesideSendAndStopAtAccessibilityTextSizes` and the camera-above-the-question checks.
 */
@RunWith(AndroidJUnit4::class)
class CallLayoutUiTest {
    @get:Rule
    val compose = createEmptyComposeRule()
    private val app = AppRobot(compose)

    @After
    fun tearDown() = app.close()

    private fun assertSentenceBesideSendAndStop() {
        for ((fixture, sentence) in listOf("signing" to Turns.THREE_CHIP_DRAFT, "notDelivered" to TURN3)) {
            app.launch("IsharaFixture" to fixture)
            app.waitFor("call.send")
            assertTrue("SEND should be enabled in the $fixture fixture", app.isEnabled("call.send"))
            assertTrue(app.exists("call.draft", sentence))
            app.assertFullyVisible("call.draft", above = "call.send")
            app.assertFullyVisible("call.status", above = "call.actionBar")
            app.assertFullyVisible("call.camera", above = "call.actionBar")
            app.closeApp()
        }
        app.launch("IsharaFixture" to "speaking")
        app.waitFor("call.stop")
        assertTrue(app.exists("call.speaking", TURN3))
        app.assertFullyVisible("call.speaking", above = "call.stop")
        app.assertFullyVisible("call.camera", above = "call.actionBar")
    }

    @Test
    fun sentenceStaysBesideSendAndStop() = assertSentenceBesideSendAndStop()

    /** Signing then speaking, the video keeps its size and place across, so nothing jumps under the user's hands. */
    @Test
    fun videoKeepsItsSizeFromSigningToSpeaking() {
        app.launch("IsharaFixture" to "signing")
        app.waitFor("call.send")
        val signing = app.bounds("call.camera")
        app.closeApp()
        app.launch("IsharaFixture" to "speaking")
        app.waitFor("call.stop")
        val speaking = app.bounds("call.camera")
        assertEquals("the video moved sideways or changed size", signing.width, speaking.width, 0.5f)
        assertEquals(signing.height, speaking.height, 0.5f)
        assertEquals(signing.left, speaking.left, 0.5f)
    }

    @Test
    fun sentenceStaysBesideSendAndStopAtTheLargestFontScale() {
        app.setFontScale(2.0f)
        assertSentenceBesideSendAndStop()
    }

    /** At the largest font the Not delivered banner still comes into view above the bar. */
    @Test
    fun notDeliveredBannerIsInViewAtTheLargestFontScale() {
        app.setFontScale(2.0f)
        app.launch("IsharaFixture" to "notDelivered")
        app.waitFor("call.deliveryBanner", "Not delivered")
        compose.waitUntil(5_000) { app.bounds("call.deliveryBanner").top < app.bounds("call.actionBar").top }
    }

    /** The first chip of the reply is reachable above the bar at the largest font. */
    @Test
    fun chipsStayReachableAtTheLargestFontScale() {
        app.setFontScale(2.0f)
        app.launch("IsharaFixture" to "signing")
        app.waitFor("chip.afternoon")
        compose.waitUntil(5_000) { app.bounds("chip.afternoon").bottom <= app.bounds("call.actionBar").top }
        app.tapPinned("chip.afternoon")
        app.waitGone("chip.afternoon")
    }

    /** The user signs the answer, so the video stays wholly above the agent's question card. */
    @Test
    fun cameraVideoStaysInViewAboveTheTimeQuestion() {
        val transcript = "sorry about the wait so what time would will would you like to come in " +
            "tomorrow or would the morning or later on in the afternoon suit her better do you think"
        app.launch("IsharaFakeOpenQuestion" to "tap", "IsharaFakeOpenQuestionText" to transcript, timeScale = "2")
        app.prepareBrief()
        app.approve()
        app.waitFor("ask.question", transcript, timeoutMs = 40_000)
        app.assertFullyVisible("call.camera", above = "call.actionBar")
        for (choice in listOf("tomorrow", "morning", "now", "wait")) {
            assertTrue("$choice runs off screen", app.bounds("ask.$choice").bottom <= app.bounds("call.actionBar").bottom + 0.5f)
        }
        app.tapPinned("ask.tomorrow")
        app.waitFor("caption.you", "Tomorrow, please.")
    }

    /**
     * Once the call is over the transcript is the screen: it runs from under the status bar to
     * Back to Home, with no box about the ending in between, and nothing can be sent.
     */
    private fun assertEndedTranscriptFillsTheScreen() {
        app.launch("IsharaFixture" to "ended")
        app.waitForEnded()
        val status = app.bounds("call.status")
        val transcript = app.bounds("call.endedPanel")
        val bar = app.bounds("call.actionBar")
        assertTrue("the transcript $transcript doesn't start under the status bar $status", transcript.top - status.bottom < 32f)
        assertTrue("the transcript $transcript stops short of the bar $bar", bar.top - transcript.bottom < 24f)
        assertFalse("an ended call explains itself in a box", app.exists("call.endedWarning"))
        val back = app.bounds("call.backHome")
        assertTrue("Back to Home $back isn't in the bar $bar", back.top >= bar.top && back.bottom <= bar.bottom + 0.5f)
    }

    @Test
    fun endedTranscriptFillsTheScreen() = assertEndedTranscriptFillsTheScreen()

    @Test
    fun endedTranscriptFillsTheScreenAtTheLargestFontScale() {
        app.setFontScale(2.0f)
        assertEndedTranscriptFillsTheScreen()
    }

    /** A hang-up the backend couldn't confirm still says so, in one line above the transcript. */
    @Test
    fun unconfirmedHangUpWarnsAboveTheTranscript() {
        app.launch("IsharaFixture" to "hangUpUnconfirmed")
        app.waitForEnded()
        app.waitFor("call.endedWarning", "Couldn't confirm the hang-up")
        assertTrue(app.bounds("call.endedWarning").bottom <= app.bounds("call.captions").top + 0.5f)
    }

    /** At the largest font the four time answers and End all stay on screen. */
    @Test
    fun timeAnswersStayReachableAtTheLargestFontScale() {
        app.setFontScale(2.0f)
        app.launch("IsharaFakeOpenQuestion" to "tap", timeScale = "2")
        app.prepareBrief()
        app.approve()
        app.waitFor("ask.question", "What time would you like", timeoutMs = 40_000)
        for (choice in listOf("tomorrow", "morning", "now", "wait")) {
            val bounds = app.bounds("ask.$choice")
            assertTrue("$choice runs off screen: $bounds", bounds.bottom <= app.bounds("call.actionBar").bottom + 0.5f)
            assertTrue("$choice is too small to tap: $bounds", bounds.height >= 44f && bounds.width >= 44f)
        }
        assertTrue(app.isEnabled("call.end"))
        assertFalse(app.exists("call.send"))
        app.tapPinned("ask.tomorrow")
        app.waitFor("caption.you", "Tomorrow, please.")
    }

    /** iOS `testRehearsedClinicCallAtAccessibilityTextSize`, first turn: the draft never hides behind the bar. */
    @Test
    fun rehearsedFirstTurnAtTheLargestFontScale() {
        app.setFontScale(2.0f)
        app.launch()
        app.startCall()
        app.waitForDraft(TURN1)
        app.assertFullyVisible("call.draft", above = "call.send")
        app.sendAndExpectDelivered(TURN1)
    }
}
