package ai.ishara.demo.ui.steer

import ai.ishara.demo.call.notification.OngoingCallNotifications
import ai.ishara.demo.support.SteerUi
import android.app.Notification
import android.app.NotificationManager
import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.performTextReplacement
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The steer flow on the fake driver, mirroring ios/IsharaUITests/SteerCallUITests.swift and
 * going further: Ishara's proposed line fills its window and goes out (or is sent now, or taken
 * over), the user steps in by typing, the call reaches its gist, Call again and Recent calls,
 * the settings gate, signing, and End call from the ongoing-call notification. Nothing is dialled.
 */
@OptIn(ExperimentalTestApi::class)
@RunWith(AndroidJUnit4::class)
class SteerCallUiTest {
    @get:Rule
    val compose = createEmptyComposeRule()

    private val ui = SteerUi(compose)

    /** The fake receptionist's lines and Ishara's answers (FakeCallDriver's steer script). */
    private val firstAgentLine = "No, 4 pm tomorrow doesn't work, sorry. Is there anything in the morning?"
    private val secondAgentLine = "Yes, 10:30 tomorrow morning works. Thank you."
    private val contact = "+91 98000 12345"

    @Before
    fun setUp() {
        SteerUi.grantNotifications()
    }

    @After
    fun tearDown() {
        ui.close()
    }

    private fun typeRequest() {
        ui.waitFor("setup.number")
        compose.onNodeWithTag("setup.number").performTextInput("9800012345")
        compose.onNodeWithTag("setup.request").performTextInput("Book a check-up next week, mornings only.")
    }

    private fun waitForCaption(tag: String, text: String, timeoutMs: Long = 15_000) = ui.waitFor(tag, text, timeoutMs)

    private fun captionExists(tag: String, text: String) = ui.exists(tag, text)

    @Test
    fun isharaRunsTheCallAndTheUserStepsInByTyping() {
        ui.launch("1", "IsharaUITestName" to "Riya")
        ui.waitFor("setup.number")
        ui.shot("01-setup-empty")
        compose.onNodeWithTag("setup.problem").assertTextContains("Enter a number, or pick someone.")
        compose.onNodeWithTag("setup.call").assertIsNotEnabled()
        typeRequest()
        ui.shot("02-setup-filled")
        compose.onNodeWithTag("setup.call").assertIsEnabled().performClick()

        // Ishara's first proposed line appears once the receptionist has spoken.
        ui.waitFor("steer.status")
        ui.shot("03-call-connecting")
        ui.waitFor("steer.proposal", timeoutMs = 20_000)
        ui.shot("04-call-proposal")
        // Doing nothing: the window runs out and the line is spoken (it appears as a caption).
        waitForCaption("caption.agent", firstAgentLine)
        ui.waitFor("steer.facts", "4 pm")

        // Step in by typing while Ishara's next line waits (the fake call, like the backend,
        // then holds that line): the typed line is previewed, then shown as the user's.
        ui.waitFor("steer.proposal", timeoutMs = 20_000)
        compose.onNodeWithTag("steer.field").performTextInput("can we do 11 instead")
        ui.waitFor("steer.status", "You're typing — Ishara is covering")
        ui.shot("05-call-typing")
        compose.onNodeWithTag("steer.send").assertIsEnabled().performClick()
        waitForCaption("caption.you", "Can we do 11 instead?")
        ui.shot("06-call-stepped-in")

        // The call runs to its end on its own and goes on to the gist by itself.
        ui.waitFor("notes.outcome", "Booked", timeoutMs = 60_000)
        compose.onNodeWithTag("notes.steppedIn").assertTextContains("You stepped in once; Ishara handled the rest.")
        ui.waitFor("notes.followUps", "Can I get the date of birth?")
        ui.shot("07-gist")
        compose.onNodeWithTag("notes.transcriptToggle").performScrollTo().performClick()
        ui.waitFor("notes.transcript", "We have 4 pm tomorrow")
        ui.shot("08-gist-transcript")

        // One tap home: the finished call's draft is cleared and the call is in Recent.
        compose.onNodeWithTag("notes.done").performClick()
        ui.waitFor("setup.number")
        assertEquals("", compose.onNodeWithTag("setup.number").fetchSemanticsNode().config.getOrNull(SemanticsProperties.EditableText)?.text)
        ui.waitFor("setup.recentPerson", contact)
        ui.waitFor("recentCalls.row", "Booked")
        ui.shot("09-setup-recent")

        // The saved call reads back its notes.
        compose.onNodeWithTag("recentCalls.row").performScrollTo().performClick()
        ui.waitFor("notes.outcome", "Booked")
        ui.waitFor("recentCall.back")
        ui.shot("10-recent-call")
        compose.onNodeWithTag("recentCall.back").performClick()
        ui.waitFor("setup.number")

        // Someone called before is one tap away.
        compose.onNode(hasText(contact, substring = true) and hasTestTag("setup.recentPerson")).performClick()
        assertEquals(
            "9800012345",
            compose.onNodeWithTag("setup.number").fetchSemanticsNode().config.getOrNull(SemanticsProperties.EditableText)?.text,
        )
    }

    @Test
    fun theProposedLineCountsDownAndCanBeSentNowOrTakenOver() {
        // A slow clock: each window runs 4 s on the fake call, so "Send now" visibly beats it.
        ui.launch("2", "IsharaUITestName" to "Riya")
        typeRequest()
        compose.onNodeWithTag("setup.call").performClick()

        ui.waitFor("steer.proposal", timeoutMs = 30_000)
        compose.onNodeWithTag("steer.proposalLabel", useUnmergedTree = true).assertTextContains("Ishara says in", substring = true)
        assertTrue("the countdown is the window's seconds", Regex("Ishara says in [0-2] s · tap to edit").matches(label()))
        val sentAt = System.currentTimeMillis()
        compose.onNodeWithTag("steer.proposalAction").performClick()
        // Spoken at once, well before its 4 s window would have run out.
        waitForCaption("caption.agent", firstAgentLine, timeoutMs = 2_500)
        assertTrue(System.currentTimeMillis() - sentAt < 3_000)
        ui.waitForGone("steer.proposal", timeoutMs = 2_000)

        // The next line: tap it to take it over. It drops into the field and is never spoken.
        ui.waitFor("steer.proposal", timeoutMs = 30_000)
        compose.onNodeWithTag("steer.proposal").performClick()
        compose.onNodeWithTag("steer.field").assertTextContains(secondAgentLine)
        ui.waitForGone("steer.proposal", timeoutMs = 3_000)
        // Ishara covers the pause instead; the cover line shows what it said.
        ui.waitFor("steer.cover", "One moment, please.", timeoutMs = 6_000)
        ui.shot("11-call-cover-line")
        Thread.sleep(5_000)
        assertFalse("a taken-over line is never spoken", captionExists("caption.agent", secondAgentLine))

        // The user's own line is previewed ("Saying your line"), then spoken as theirs.
        compose.onNodeWithTag("steer.field").performTextReplacement("Yes, 10:30 works, thanks")
        compose.onNodeWithTag("steer.send").performClick()
        ui.waitFor("steer.proposalLabel", "Saying your line · tap to edit", timeoutMs = 5_000, unmerged = true)
        ui.waitFor("steer.youTyped", "You typed: \u201CYes, 10:30 works, thanks\u201D")
        ui.shot("12-call-user-preview")
        waitForCaption("caption.you", "Yes, 10:30 works, thanks.", timeoutMs = 10_000)
    }

    private fun label(): String =
        compose.onNodeWithTag("steer.proposalLabel", useUnmergedTree = true).fetchSemanticsNode().config.getOrNull(SemanticsProperties.Text)
            ?.joinToString("") { it.text }.orEmpty()

    @Test
    fun aCallNeedsTheCallersNameFirst() {
        SteerUi.clearSettings(ui.context)
        ui.launch("0.05")
        typeRequest()
        compose.onNodeWithTag("setup.call").performClick()

        ui.waitFor("settings.reason")
        compose.onNodeWithTag("settings.done").assertIsNotEnabled()
        ui.shot("13-settings-for-call")
        // Cancel places no call.
        compose.onNodeWithTag("settings.cancel").performClick()
        ui.waitForGone("settings.sheet")
        assertFalse(ui.exists("steer.status"))

        compose.onNodeWithTag("setup.call").performClick()
        ui.waitFor("settings.name")
        compose.onNodeWithTag("settings.name").performTextInput("Riya Sharma ")
        compose.onNodeWithTag("settings.done").assertIsEnabled().performClick()
        ui.waitFor("steer.status")
        ui.waitFor("caption.agent", "Riya Sharma", timeoutMs = 10_000)
        compose.onNodeWithTag("steer.end").performClick()
    }

    @Test
    fun settingsKeepTheNameAndTheCallback() {
        SteerUi.clearSettings(ui.context)
        ui.launch("0.05")
        ui.waitFor("setup.settings")
        compose.onNodeWithTag("setup.settings").performClick()
        ui.waitFor("settings.name")
        assertFalse("opened from its button, it doesn't ask for a call", ui.exists("settings.reason"))
        compose.onNodeWithTag("settings.name").performTextInput("Asha Rao")
        compose.onNodeWithTag("settings.callback").performTextInput("+91 98000 54321")
        compose.onNodeWithTag("settings.callback").assertTextContains("9800054321")
        ui.shot("14-settings")
        compose.onNodeWithTag("settings.done").performClick()
        ui.waitForGone("settings.sheet")
        ui.waitFor("setup.settings")
        compose.onNode(hasText("Hi Asha")).assertExists()
    }

    @Test
    fun signingStepsInAndTypingTakesOver() {
        ui.launch("1", "IsharaUITestName" to "Riya")
        typeRequest()
        compose.onNodeWithTag("setup.call").performClick()
        ui.waitFor("steer.status", "Ishara is handling it — step in any time", timeoutMs = 15_000)

        compose.onNodeWithTag("steer.sign").performClick()
        ui.waitFor("steer.signing")
        ui.waitFor("steer.status", "You're signing — Ishara waits for you")
        compose.onNodeWithTag("steer.sendSigned").assertIsNotEnabled()
        ui.shot("15-call-signing")

        compose.onNodeWithTag("steer.type").performClick()
        ui.waitForGone("steer.signing")
        ui.waitFor("steer.field")
        ui.waitFor("steer.status", "Ishara is handling it — step in any time")
        compose.onNodeWithTag("steer.end").performClick()
    }

    @Test
    fun endCallInTheNotificationEndsTheCallAndCallAgainStartsANewOne() {
        ui.launch("1", "IsharaUITestName" to "Riya")
        typeRequest()
        compose.onNodeWithTag("setup.call").performClick()
        ui.waitFor("steer.status", "Ishara is handling it — step in any time", timeoutMs = 15_000)

        val notification = waitForNotification { it.extras.getCharSequence(Notification.EXTRA_TITLE)?.toString() == contact }
        assertTrue("the call keeps running while the app is away", notification.flags and Notification.FLAG_FOREGROUND_SERVICE != 0)
        assertTrue(notification.flags and Notification.FLAG_ONGOING_EVENT != 0)
        assertEquals("Answering for you", notification.extras.getCharSequence(Notification.EXTRA_SUB_TEXT)?.toString())
        assertTrue("a running timer", notification.extras.getBoolean(Notification.EXTRA_SHOW_CHRONOMETER))
        val end = notification.actions.singleOrNull { it.title.toString() == "End call" }
        assertNotNull("End call is offered", end)
        ui.waitFor("caption.agent")
        // The latest line follows the call.
        waitForNotification { it.extras.getCharSequence(Notification.EXTRA_TEXT)?.toString()?.startsWith("\u201C") == true }

        end!!.actionIntent.send()
        ui.waitFor("steer.status", "Call ended", timeoutMs = 5_000)
        waitForCaption("caption.agent", "Goodbye.", timeoutMs = 5_000)
        assertTrue("the ongoing notification goes with the call", waitUntil { activeNotification(OngoingCallNotifications.ONGOING_ID) == null })
        assertNull("the app is open, so no 'call ended' notice", activeNotification(OngoingCallNotifications.ENDED_ID))
        ui.shot("16-call-ended")

        ui.waitFor("notes.callAgain", timeoutMs = 10_000)
        compose.onNodeWithTag("notes.callAgain").performClick()
        ui.waitFor("steer.end", timeoutMs = 10_000)
        ui.waitFor("steer.status")
        waitForNotification { it.extras.getCharSequence(Notification.EXTRA_TITLE)?.toString() == contact }
        compose.onNodeWithTag("steer.end").performClick()
        ui.waitFor("steer.gist", timeoutMs = 5_000)
    }

    private fun activeNotification(id: Int): Notification? =
        ui.context.getSystemService(NotificationManager::class.java).activeNotifications.firstOrNull { it.id == id }?.notification

    private fun waitForNotification(matches: (Notification) -> Boolean): Notification {
        var found: Notification? = null
        assertTrue(
            "the ongoing-call notification is posted",
            waitUntil { activeNotification(OngoingCallNotifications.ONGOING_ID)?.takeIf(matches)?.also { found = it } != null },
        )
        return found!!
    }

    private fun waitUntil(timeoutMs: Long = 10_000, condition: () -> Boolean): Boolean {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < deadline) {
            if (condition()) return true
            Thread.sleep(50)
        }
        return false
    }
}
