package ai.ishara.demo.app

import ai.ishara.demo.MainActivity
import ai.ishara.demo.support.SteerUi
import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import android.content.Intent
import org.junit.After
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Walks the app on the device in test mode, like ios/IsharaUITests/DemoCallUITests.swift: the
 * fake call on a fast clock, the real Swift `TurnStore`, and the screens found by the iOS
 * accessibility identifiers (Compose test tags).
 */
@OptIn(ExperimentalTestApi::class)
@RunWith(AndroidJUnit4::class)
class DemoCallUiTest {
    @get:Rule
    val compose = createEmptyComposeRule()

    private var scenario: ActivityScenario<MainActivity>? = null

    @After
    fun tearDown() {
        scenario?.close()
    }

    private fun launch(vararg extras: Pair<String, String>) {
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("IsharaDriver", "fake")
            .putExtra("IsharaCallHistory", "memory")
            .putExtra("IsharaFakeTimeScale", "0.05")
        extras.forEach { (key, value) -> intent.putExtra(key, value) }
        scenario = ActivityScenario.launch(intent)
    }

    private fun waitFor(tag: String, text: String? = null, timeoutMs: Long = 10_000) {
        val matcher = if (text == null) hasTestTag(tag) else hasTestTag(tag) and hasText(text, substring = true)
        compose.waitUntilAtLeastOneExists(matcher, timeoutMs)
    }

    @Test
    fun rehearsedClinicCallFromHomeToSendToEnd() {
        launch("IsharaFlow" to "classic")
        waitFor("home.call")
        compose.onNodeWithTag("callingNumberNote").assertExists()
        compose.onNodeWithTag("home.call").performClick()

        waitFor("getReady.start")
        compose.waitUntil(10_000) { runCatching { compose.onNodeWithTag("getReady.start").assertIsEnabled() }.isSuccess }
        compose.onNodeWithTag("getReady.start").performClick()

        // Turn 1: the signed chips, then the draft. Nothing is spoken before SEND.
        waitFor("chip.tomorrow")
        waitFor("call.draft", "Hello, I'd like a doctor's appointment tomorrow.")
        compose.onNodeWithTag("call.send").assertIsEnabled().performClick()

        // Spoken: the reply joins the captions as the user's, and SEND is off until the next reply.
        waitFor("caption.you", "Hello, I'd like a doctor's appointment tomorrow.")
        waitFor("call.deliveryBanner", "Delivered")
        compose.onNodeWithTag("call.send").assertIsNotEnabled()

        // Turn 2 brings the planned wrong chip; End wipes it and sends nothing more.
        waitFor("chip.afternoon")
        compose.onNodeWithTag("call.end").performClick()
        waitFor("call.status", "Call ended")
        waitFor("call.endedPanel")
        waitFor("caption.agent", "Goodbye.")
        compose.onNodeWithTag("call.backHome").performClick()
        waitFor("home.call")
        waitFor("recentCalls.row", "City Clinic")
    }

    @Test
    fun notDeliveredReplyIsOnlyResentAfterSendIsTappedAgain() {
        launch("IsharaFlow" to "classic", "IsharaFakeNotDelivered" to "YES")
        waitFor("home.call")
        compose.onNodeWithTag("home.call").performClick()
        compose.waitUntil(10_000) { runCatching { compose.onNodeWithTag("getReady.start").assertIsEnabled() }.isSuccess }
        compose.onNodeWithTag("getReady.start").performClick()

        waitFor("call.draft", "Hello, I'd like a doctor's appointment tomorrow.")
        compose.onNodeWithTag("call.send").performClick()
        waitFor("chip.afternoon")
        compose.onNodeWithTag("chip.afternoon").performClick()
        waitFor("call.draft", "No, sorry, 4 pm doesn't work.")
        compose.onNodeWithTag("call.send").performClick()

        waitFor("call.deliveryBanner", "Not delivered")
        waitFor("call.draft", "Not delivered")
        compose.onNodeWithTag("call.send").assertIsEnabled().performClick()
        waitFor("caption.you", "No, sorry, 4 pm doesn't work.")
    }

    @Test
    fun steerCallFromTheTypedRequestToItsGist() {
        SteerUi.grantNotifications()
        launch("IsharaUITestName" to "Riya")
        waitFor("setup.number")
        compose.onNodeWithTag("setup.number").performTextInput("9800012345")
        compose.onNodeWithTag("setup.request").performTextInput("Book a doctor's appointment tomorrow morning")
        compose.onNodeWithTag("setup.call").assertIsEnabled().performClick()

        waitFor("steer.status")
        waitFor("steer.facts", "tomorrow", timeoutMs = 15_000)
        waitFor("notes.outcome", "Booked", timeoutMs = 30_000)
        compose.onNodeWithTag("notes.done").performClick()
        waitFor("setup.number")
    }
}
