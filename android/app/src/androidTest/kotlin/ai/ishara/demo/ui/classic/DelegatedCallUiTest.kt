package ai.ishara.demo.ui.classic

import ai.ishara.demo.ui.classic.Turns.CALLBACK_LINE
import ai.ishara.demo.ui.classic.Turns.OFFER
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextReplacement
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.After
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * "Call for me" (decision D9) through the real screens on the fake call: Home → Get ready →
 * sign or tap the request → read the brief → approve it once → the agent's call → the notes.
 * Mirrors ios/IsharaUITests/DelegatedCallUITests.swift and DelegatedEdgeCaseUITests.swift.
 */
@RunWith(AndroidJUnit4::class)
class DelegatedCallUiTest {
    @get:Rule
    val compose = createEmptyComposeRule()
    private val app = AppRobot(compose)

    @After
    fun tearDown() = app.close()

    private val timeAnswers = mapOf(
        "tomorrow" to "Tomorrow, please. What times are available?",
        "morning" to "In the morning, please. What times are available?",
        "now" to "Today, as soon as possible, please. What times are available?",
        "wait" to "One moment, please, I'm checking.",
    )

    @Test
    fun attendedCallForMeAsksThenBooks() {
        app.launch()
        app.prepareBrief()
        app.approve()

        app.waitFor("call.delegatedNote", "When a decision is yours")
        assertFalse("a delegated call has no SEND", app.exists("call.send"))
        assertTrue("an attended call keeps the camera to answer by signing", app.exists("call.camera"))
        app.waitFor("ask.question", "10:30 tomorrow morning")
        app.tapPinned("ask.yes")

        app.openNotes()
        app.waitFor("notes.outcome", "Booked")
        app.tapPinned("notes.done")
        app.waitFor("home.callForMe")
    }

    /** Version B: the receptionist asks "when?"; the fake call signs TOMORROW, then YES books it. */
    @Test
    fun openTimeQuestionAnsweredBySigningTomorrowThenYesBooks() {
        app.launch("IsharaFakeOpenQuestion" to "tomorrow")
        app.prepareBrief()
        app.approve()

        app.waitFor("ask.question", "What time would you like")
        app.waitFor("caption.you", "Tomorrow, please. What times are available?", 20_000)
        app.waitFor("ask.question", "10:30 tomorrow morning", 20_000)
        app.tapPinned("ask.yes")
        app.openNotes()
        app.waitFor("notes.outcome", "Booked")
    }

    /** By tap: the card offers the time words and WAIT, each with its exact sentence; MORNING speaks exactly its own. */
    @Test
    fun openTimeQuestionTappedMorningSpeaksExactlyItsSentence() {
        app.launch("IsharaFakeOpenQuestion" to "tap")
        app.prepareBrief()
        app.approve()

        app.waitFor("ask.question", "What time would you like")
        for ((choice, sentence) in timeAnswers) {
            assertTrue("no $choice answer showing \u201C$sentence\u201D", app.exists("ask.$choice", sentence))
        }
        assertFalse("yes is no answer to \"what time?\"", app.exists("ask.yes"))
        app.tapPinned("ask.morning")

        app.waitFor("caption.you", timeAnswers.getValue("morning"))
        app.waitFor("ask.question", "10:30 tomorrow morning", 20_000)
        app.tapPinned("ask.yes")
        app.openNotes()
        app.waitFor("notes.outcome", "Booked")
    }

    /** The sentence on the tapped button is exactly what the agent says for the user. */
    @Test
    fun tappedAnswerSpeaksExactlyTheShownSentence() {
        val no = "No, 10:30 tomorrow doesn't work, sorry. Is there another time?"
        app.launch()
        app.prepareBrief()
        app.approve()

        app.waitFor("ask.question", OFFER)
        assertTrue("NO doesn't show its sentence", app.exists("ask.no", no))
        assertTrue(app.exists("ask.yes", "Yes, 10:30 tomorrow works. Thank you."))
        assertTrue(app.exists("ask.wait", "One moment, please, I'm checking."))
        app.tapPinned("ask.no")

        app.waitFor("caption.you", no)
        app.waitGone("ask.question")
        app.openNotes()
        app.waitFor("notes.done")
        compose.onNodeWithTag("notes.outcome").assertExists()
    }

    @Test
    fun unattendedCallShowsNoCameraAndNoQuestionAndComesBackAsACallback() {
        app.launch()
        app.prepareBrief()
        app.setAttended(false)
        app.approve()

        app.waitFor("call.delegatedNote", "put the phone down")
        compose.waitUntil(40_000) {
            assertFalse("an unattended call asked a question", app.exists("ask.question"))
            assertFalse("an unattended call shows the camera", app.exists("camera.pill"))
            assertFalse("an unattended call shows the camera", app.exists("call.camera"))
            app.exists("call.notes")
        }
        assertTrue(app.captionExists("caption.agent", CALLBACK_LINE))
        app.openNotes()
        app.waitFor("notes.outcome", "call back")
    }

    @Test
    fun briefCanNotBeApprovedUntilPrepared() {
        app.launch()
        app.waitFor("home.callForMe")
        app.tapPinned("home.callForMe")
        app.waitEnabled("getReady.start", 20_000)
        app.tapPinned("getReady.start")
        app.waitFor("brief.add.tomorrow")
        assertFalse("Approve was offered before signing", app.exists("brief.approve"))
        app.tap("brief.add.tomorrow")
        app.tap("brief.add.morning")
        assertFalse("Approve was offered before the brief was built", app.exists("brief.approve"))
        assertFalse(app.exists("brief.text"))
        app.tapPinned("brief.prepare")
        app.waitFor("brief.text", "Preferred: tomorrow in the morning.")
        app.waitFor("brief.approve")
    }

    /** The brief is built below the details; it must come into view above Approve. */
    @Test
    fun preparedBriefScrollsIntoViewAboveApprove() {
        app.launch()
        app.prepareBrief()
        compose.waitUntil(3_000) { app.bounds("brief.text").bottom <= app.bounds("brief.actionBar").top }
    }

    /** Any edit after the brief was built hides it until rebuilt; the attended choice keeps it. */
    @Test
    fun editingAfterPreparingHidesTheBriefUntilRebuilt() {
        app.launch()
        app.prepareBrief()

        app.setAttended(false)
        assertTrue("the attended switch hid the brief", app.exists("brief.approve"))

        app.tap("chip.morning")
        app.waitGone("brief.approve")
        assertFalse(app.exists("brief.text"))
        app.tapPinned("brief.prepare")
        app.waitFor("brief.text", "Preferred: tomorrow.")

        compose.onNodeWithTag("brief.name").performScrollTo().performTextReplacement("Riya K")
        app.waitGone("brief.approve")
        app.tapPinned("brief.prepare")
        app.waitFor("brief.text", "Riya K")
    }

    /** The backend goes away while the question is open: no answer offered, notes say why, Refresh keeps saying it. */
    @Test
    fun backendGoingAwayDuringTheCallAndOnTheNotes() {
        app.launch("IsharaFakeConnectionDrop" to "staysDown", timeScale = "0.5")
        app.prepareBrief()
        app.approve()
        app.waitFor("ask.question", OFFER)

        app.waitFor("call.connectionLostPanel", timeoutMs = 20_000)
        assertFalse("a question was still offered with the connection gone", app.exists("ask.yes"))
        app.openNotes(20_000)

        app.waitFor("notes.failure", "notes couldn")
        assertFalse(app.exists("notes.outcome"))
        app.waitEnabled("notes.refresh")
        app.tapPinned("notes.refresh")
        app.waitEnabled("notes.refresh")
        assertTrue("Refresh lost the explanation", app.exists("notes.failure", "notes couldn"))
        app.tapPinned("notes.done")
        app.waitFor("home.callForMe")
    }

    /** Bolna's summary lands after the call ended; the open notes pick it up without a Refresh. */
    @Test
    fun notesPickUpBolnasLateSummaryWithoutARefresh() {
        app.launch("IsharaFakeBolnaSummary" to "12", timeScale = "0.5")
        app.prepareBrief()
        app.setAttended(false)
        app.approve()
        app.openNotes()
        app.waitFor("notes.outcome", "call back")
        assertFalse("the summary was there before Bolna sent it", app.exists("notes.bolnaSummary"))
        app.waitFor("notes.bolnaSummary", "The agent called to book a doctor's appointment for Riya.", 30_000)
    }

    @Test
    fun notesMarkTheAutomaticSummaryAsFallibleAndShowTheTranscript() {
        app.launch("IsharaFixture" to "notes")
        app.waitFor("notes.outcome", "Booked")
        // A transcript row: who spoke, then what they said.
        compose.onNode(hasText("They said", substring = true) and hasText("Great, you're booked for 10:30 tomorrow morning.", substring = true))
            .performScrollTo()
        compose.onNodeWithTag("notes.bolnaSummary").performScrollTo()
        compose.onNodeWithText("It can be wrong; the transcript is what was said.", substring = true, useUnmergedTree = true).performScrollTo()
    }
}
