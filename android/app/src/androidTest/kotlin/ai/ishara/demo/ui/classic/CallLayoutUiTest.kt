package ai.ishara.demo.ui.classic

import ai.ishara.demo.ui.classic.Turns.TURN1
import ai.ishara.demo.ui.classic.Turns.TURN3
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.After
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The call screen's layout rules at the default and the largest font scale (Android's Dynamic
 * Type), on the debug fixtures: the sentence SEND or STOP acts on is wholly readable right
 * above its button, and the controls that matter stay on screen. Mirrors iOS
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
            app.closeApp()
        }
        app.launch("IsharaFixture" to "speaking")
        app.waitFor("call.stop")
        assertTrue(app.exists("call.speaking", TURN3))
        app.assertFullyVisible("call.speaking", above = "call.stop")
    }

    @Test
    fun sentenceStaysBesideSendAndStop() = assertSentenceBesideSendAndStop()

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

    /** The user signs the answer, so the camera stays wholly above the agent's question card. */
    @Test
    fun cameraStaysInViewAboveTheTimeQuestion() {
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
