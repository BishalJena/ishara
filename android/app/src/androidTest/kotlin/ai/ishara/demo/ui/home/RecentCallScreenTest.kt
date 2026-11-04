package ai.ishara.demo.ui.home

import ai.ishara.demo.core.call.CallMode
import ai.ishara.demo.core.call.CallNotes
import ai.ishara.demo.core.call.CaptionSpeaker
import ai.ishara.demo.core.call.TranscriptEntry
import ai.ishara.demo.models.CallRecord
import ai.ishara.demo.ui.theme.IsharaTheme
import androidx.activity.ComponentActivity
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** A saved call read back: the shared notes sections when it has notes, else its captions. */
@RunWith(AndroidJUnit4::class)
class RecentCallScreenTest {
    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private val record = CallRecord(
        id = "6F9619FF-8B86-D011-B42D-00C04FC964FF",
        date = 1_793_000_000.0,
        contactName = "City Clinic",
        mode = CallMode.LIVE,
        captions = listOf(
            CallRecord.Line(CallRecord.Line.Speaker.RECEPTIONIST, "City Clinic, how can I help?", 1.0),
            CallRecord.Line(CallRecord.Line.Speaker.AGENT, "Hello, tomorrow please.", 2.0),
        ),
    )

    private fun show(record: CallRecord?, onBack: () -> Unit = {}, onDelete: () -> Unit = {}) {
        compose.setContent { IsharaTheme { RecentCallScreen(record, onBack, onDelete) } }
    }

    @Test
    fun withoutNotesShowsTheCaptionsWithWhoSpoke() {
        show(record)
        compose.onNodeWithTag("notes.outcome").assertTextContains("You signed the call")
        compose.onNodeWithText("CALL WITH CITY CLINIC", ignoreCase = true).assertExists()
        compose.onNodeWithText("Receptionist").assertExists()
        compose.onNodeWithText("City Clinic, how can I help?").assertExists()
        compose.onNodeWithText("Ishara (voice)").assertExists()
        compose.onNodeWithText("Hello, tomorrow please.").assertExists()
        compose.onNodeWithText("No captions in this call.").assertDoesNotExist()
    }

    @Test
    fun withoutCaptionsSaysSo() {
        show(record.copy(captions = emptyList()))
        compose.onNodeWithText("No captions in this call.").assertExists()
    }

    @Test
    fun withNotesShowsTheNotesInsteadOfTheCaptions() {
        val notes = CallNotes(
            callId = "call-1",
            mode = CallMode.DELEGATED,
            ready = true,
            outcome = "booked",
            summary = listOf("Booked for tomorrow at four."),
            openQuestions = listOf("Bring the referral?"),
            transcript = listOf(TranscriptEntry(CaptionSpeaker.RECEPTIONIST, "Four works.", 1.0)),
            bolnaSummary = "The caller booked a visit.",
        )
        show(record.copy(mode = CallMode.DELEGATED, notes = notes))
        compose.onNodeWithTag("notes.outcome").assertTextContains("Booked")
        compose.onNodeWithText("Booked for tomorrow at four.").assertExists()
        compose.onNodeWithText("Bring the referral?").assertExists()
        compose.onNodeWithText("They said").assertExists()
        compose.onNodeWithTag("notes.bolnaSummary").performScrollTo().assertTextContains("The caller booked a visit.")
        compose.onNodeWithText("City Clinic, how can I help?").assertDoesNotExist()
    }

    @Test
    fun backAndDeleteReachTheirCallbacks() {
        val taps = mutableListOf<String>()
        show(record, onBack = { taps += "back" }, onDelete = { taps += "delete" })
        compose.onNodeWithTag("recentCall.back").performClick()
        compose.onNodeWithTag("recentCall.delete").performClick()
        assertEquals(listOf("back", "delete"), taps)
    }

    @Test
    fun aDeletedCallShowsNothingButBack() {
        show(null)
        compose.onNodeWithTag("recentCall.back").assertExists()
        compose.onNodeWithTag("recentCall.delete").assertDoesNotExist()
        compose.onNodeWithTag("notes.outcome").assertDoesNotExist()
    }
}
