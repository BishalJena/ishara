package ai.ishara.demo.ui.classic

import ai.ishara.demo.ui.classic.Turns.THREE_CHIP_DRAFT
import ai.ishara.demo.ui.classic.Turns.TURN1
import ai.ishara.demo.ui.classic.Turns.TURN3
import ai.ishara.demo.ui.classic.Turns.TURN5
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.doubleClick
import androidx.compose.ui.test.performTouchInput
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The classic call (sign every reply, approve it with SEND) through the real screens on the fake
 * call, mirroring ios/IsharaUITests/DemoCallUITests.swift and CallEdgeCaseUITests.swift. Each
 * test checks the safety rule its case is about: nothing is spoken without SEND, an approval
 * speaks once, a stale or removed draft can't be sent, and a drop or End leaves nothing to send.
 */
@RunWith(AndroidJUnit4::class)
class ClassicCallUiTest {
    @get:Rule
    val compose = createEmptyComposeRule()
    private val app = AppRobot(compose)

    @After
    fun tearDown() = app.close()

    @Test
    fun rehearsedClinicCallEndToEnd() {
        app.launch()
        app.startCall()

        // Turn 0: the agent's disclosure, the only line said without a SEND at the start.
        app.waitFor("caption.agent", "calling for a Deaf caller")

        // Turn 1: hello · doctor · tomorrow → LLM draft. Nothing is spoken until SEND.
        app.waitForDraft(TURN1)
        assertFalse("a reply was spoken before SEND", app.exists("caption.you"))
        app.sendAndExpectDelivered(TURN1)

        // Turn 2: the receptionist's caption.
        app.waitFor("caption.receptionist", "We have 4 pm tomorrow. Does that work?")

        // Turn 3: no · afternoon · morning, then the wrong chip is removed with ✕.
        app.waitForDraft("In the morning")
        app.tap("chip.afternoon")
        app.waitGone("chip.afternoon")
        assertTrue(app.exists("chip.no"))
        assertTrue(app.exists("chip.morning"))
        app.waitForDraft(TURN3)
        app.sendAndExpectDelivered(TURN3)

        // Turn 4: the receptionist offers 10:30.
        app.waitFor("caption.receptionist", "Yes, 10:30 tomorrow morning.")

        // Turn 5: yes · [?] · thankyou. The unsure chip shows but isn't spoken.
        app.waitForDraft(TURN5)
        assertTrue(app.exists("chip.unsure"))
        app.sendAndExpectDelivered(TURN5)
        assertFalse("the unsure chip leaked into the spoken reply", app.text("caption.you", TURN5).contains("?"))

        // Turn 6: End. Nothing more can be sent; the captions stay as a read-only transcript.
        app.tapPinned("call.end")
        app.waitForEnded()
        assertFalse(app.exists("call.send"))
        assertTrue("the transcript was wiped on End", app.captionExists("caption.you", TURN5))
        assertTrue(app.captionExists("caption.receptionist", "Yes, 10:30 tomorrow morning."))
        assertTrue("the agent's goodbye is in the transcript", app.captionExists("caption.agent", "Goodbye"))
        app.tapPinned("call.backHome")
        app.waitFor("home.call")
        app.waitFor("recentCalls.row", "City Clinic")
    }

    /** At a fast clock Get ready finishes, and the first draft arrives, before the first look (iOS #31). */
    @Test
    fun callStartsWhenTheTimersFinishBeforeTheFirstLook() {
        app.launch(timeScale = "0.05")
        app.startCall()
        app.waitForDraft(TURN1)
    }

    /** Start stays disabled while Get ready is checking; the slow clock keeps the checks going. */
    @Test
    fun startCallStaysDisabledWhileTheChecksRun() {
        app.launch(timeScale = "20")
        app.waitFor("home.call")
        app.tapPinned("home.call")
        app.waitFor("getReady.start")
        for (check in listOf("face", "both_hands", "light")) {
            assertTrue("no $check check", app.exists("getReady.check.$check"))
            assertTrue("$check passed already", app.text("getReady.check.$check").contains("checking"))
        }
        assertFalse("Start call was enabled before the checks passed", app.isEnabled("getReady.start"))
        app.assertStays("Start disabled", 2.0) { !app.isEnabled("getReady.start") }
    }

    /** Hands at rest cost nothing: with a draft ready and no tap, nothing is spoken. */
    @Test
    fun longPauseSpeaksNothing() {
        app.launch(timeScale = "0.5")
        app.startCall()
        app.waitForDraft(TURN1)
        // 8 s at half speed is 16 s of the scripted call: past Bolna's 15 s silence line.
        app.assertStays("a silent pause", 8.0) {
            !app.exists("caption.you") && app.exists("call.draft", TURN1) && app.isEnabled("call.send") && !app.exists("call.stop")
        }
        assertFalse("a delivery result appeared without SEND", app.exists("call.deliveryBanner"))
    }

    /** A wrong chip removed before SEND: its draft can't be sent, and its word never reaches the call. */
    @Test
    fun removedChipsDraftCanNotBeSent() {
        app.launch()
        app.startCall()
        app.waitForDraft(TURN1)
        app.sendAndExpectDelivered(TURN1)

        app.waitForDraft(THREE_CHIP_DRAFT)
        app.tap("chip.afternoon")
        compose.waitForIdle()
        assertFalse("the stale draft is still offered", app.exists("call.draft", THREE_CHIP_DRAFT))
        assertTrue("SEND was enabled with a stale draft", !app.isEnabled("call.send") || app.exists("call.draft", TURN3))
        app.waitForDraft(TURN3)
        app.sendAndExpectDelivered(TURN3)
        assertEquals("the removed chip was spoken", 0, app.count("caption.you", "afternoon"))
    }

    /** A double tap on SEND approves the draft once: spoken once, and the second tap doesn't stop it. */
    @Test
    fun doubleSendSpeaksOnce() {
        app.launch()
        app.startCall()
        app.waitForDraft(TURN1)
        app.waitEnabled("call.send")
        compose.onNodeWithTag("call.send").performTouchInput { doubleClick() }

        app.waitFor("call.deliveryBanner", "Delivered", 20_000)
        assertFalse("the second tap stopped the reply", app.exists("call.deliveryBanner", "Stopped"))
        app.assertCount(1, "caption.you", TURN1)
        app.assertStays("one spoken copy", 3.0) { app.count("caption.you", TURN1) == 1 }
    }

    /** "Not delivered" is never resent by itself; only a new tap on SEND speaks it again. */
    @Test
    fun notDeliveredIsResentOnlyOnANewTap() {
        app.launch("IsharaFakeNotDelivered" to "YES")
        app.startCall()
        app.waitForDraft(TURN1)
        app.sendAndExpectDelivered(TURN1)
        app.waitForDraft(THREE_CHIP_DRAFT)
        app.tap("chip.afternoon")
        app.waitForDraft(TURN3)
        app.tapPinned("call.send")

        app.waitFor("call.deliveryBanner", "Not delivered")
        // The badge merges into the draft card, which TalkBack reads as one.
        app.waitFor("call.draft", "Not delivered")
        app.assertStays("the unspoken reply waiting for a tap", 4.0) {
            app.count("caption.you", TURN3) == 0 && !app.exists("call.stop") && app.exists("call.draft", TURN3) && app.isEnabled("call.send")
        }
        app.sendAndExpectDelivered(TURN3)
        app.assertCount(1, "caption.you", TURN3)
    }

    /** The receptionist talks over the reply: their words show, STOP stays, the reply isn't cut off. */
    @Test
    fun receptionistTalkingOverTheReplyDoesNotCutItOff() {
        app.launch("IsharaFakeInterrupt" to "YES", timeScale = "0.5")
        app.startCall()
        app.waitForDraft(TURN1)
        app.tapPinned("call.send")

        app.waitFor("caption.receptionist", "who's calling")
        assertTrue("STOP went away when the receptionist spoke", app.exists("call.stop"))
        assertTrue(app.exists("call.speaking", TURN1))
        app.waitFor("call.deliveryBanner", "Delivered", 20_000)
        app.assertCount(1, "caption.you", TURN1)
    }

    /** STOP while the reply is being spoken: nothing is said, and the draft waits for a new SEND. */
    @Test
    fun stopWhileSpeakingSpeaksNothing() {
        app.launch(timeScale = "1")
        app.startCall()
        app.waitForDraft(TURN1, timeoutMs = 40_000)
        app.tapPinned("call.send")
        app.waitFor("call.stop")
        assertTrue("the sentence being spoken isn't next to STOP", app.exists("call.speaking", TURN1))
        app.tapPinned("call.stop")

        app.waitFor("call.deliveryBanner", "Stopped. Nothing was spoken.")
        app.waitFor("call.draft", "Stopped")
        assertFalse("a stopped reply was shown as spoken", app.exists("caption.you", TURN1))
        assertTrue("SEND must stay available to send it anyway", app.isEnabled("call.send"))
    }

    /** The backend goes away with a draft on screen: it is wiped, SEND is off, nothing is resent after. */
    @Test
    fun lostConnectionWipesTheReplyAndResendsNothing() {
        app.launch("IsharaFakeConnectionDrop" to "reconnects", timeScale = "0.5")
        app.startCall()
        app.waitForDraft(TURN1)

        app.waitFor("call.connectionLostPanel", "Chips and draft were wiped")
        assertTrue(app.exists("call.status", "reconnecting"))
        assertFalse("the draft outlived the lost connection", app.exists("call.draft"))
        assertFalse("chips outlived the lost connection", app.exists("chip.hello"))
        assertFalse(app.isEnabled("call.send"))
        assertFalse(app.isEnabled("quickReply.yes"))
        assertTrue("End must stay in reach", app.isEnabled("call.end"))

        app.waitFor("call.status", "In call", 20_000)
        app.assertStays("nothing resent after the reconnect", 4.0) {
            !app.exists("caption.you") && !app.exists("chip.hello") && !app.exists("call.draft", TURN1) && !app.isEnabled("call.send")
        }
    }

    /** The connection doesn't come back: no promise of a reconnect, and End still ends the call. */
    @Test
    fun connectionThatStaysDownLeavesOnlyEnd() {
        app.launch("IsharaFakeConnectionDrop" to "staysDown", timeScale = "0.5")
        app.startCall()
        app.waitForDraft(TURN1)

        app.waitFor("call.connectionLostPanel", "couldn't be restored", 20_000)
        assertFalse(app.exists("call.connectionLostPanel", "Reconnecting"))
        assertFalse(app.isEnabled("call.send"))
        app.tapPinned("call.end")
        app.waitForEnded()
        assertFalse(app.exists("caption.you"))
    }

    /** End with a draft on screen: the call ends, the draft is wiped and never spoken. */
    @Test
    fun endMidDraftSpeaksNothing() {
        app.launch()
        app.startCall()
        app.waitForDraft(TURN1)
        app.tapPinned("call.end")

        app.waitForEnded()
        assertFalse(app.exists("call.send"))
        assertFalse("the unsent draft outlived End", app.exists("call.draft"))
        app.assertStays("silence after End", 3.0) { !app.exists("caption.you") }
        assertTrue(app.captionExists("caption.agent", "Goodbye"))
    }

    /** Pick-one (D8 grey zone): "Did you mean …?" becomes a chip only when tapped. */
    @Test
    fun pickOneBecomesAChipOnlyWhenTapped() {
        app.launch("IsharaReplay" to "tomorrow?")
        app.startCall()
        app.waitFor("candidate.accept")
        assertTrue(app.text("candidate.accept").contains("tomorrow"))
        assertFalse("a pick-one became a chip before it was tapped", app.exists("chip.tomorrow"))
        assertFalse("SEND was enabled for an untapped pick-one", app.isEnabled("call.send"))
        app.tap("candidate.accept")
        app.waitFor("chip.tomorrow")
        app.waitGone("candidate.accept")
    }

    @Test
    fun dismissedPickOneLeavesNothing() {
        app.launch("IsharaReplay" to "tomorrow?")
        app.startCall()
        app.waitFor("candidate.dismiss")
        app.tap("candidate.dismiss")
        app.waitGone("candidate.accept")
        app.assertStays("no chip after No", 2.0) { !app.exists("chip.tomorrow") && !app.isEnabled("call.send") }
    }

    /** An unsure sign is a red [?] chip, never sent: SEND stays off with nothing else to say. */
    @Test
    fun unsureSignIsAChipThatIsNeverSent() {
        app.launch("IsharaReplay" to "?")
        app.startCall()
        app.waitFor("chip.unsure")
        assertFalse("the call screen offered to send an unsure sign", app.isEnabled("call.send"))
        assertFalse(app.exists("call.framingHint"))
        app.assertStays("nothing spoken for [?]", 2.0) { !app.exists("caption.you") && !app.isEnabled("call.send") }
    }

    /** A hand left the picture during the sign: the [?] chip plus the framing hint. */
    @Test
    fun handOutOfFrameShowsTheFramingHint() {
        app.launch("IsharaReplay" to "frame")
        app.startCall()
        app.waitFor("call.framingHint", "A hand left the picture")
        assertTrue(app.exists("chip.unsure"))
        assertFalse(app.isEnabled("call.send"))
    }
}
