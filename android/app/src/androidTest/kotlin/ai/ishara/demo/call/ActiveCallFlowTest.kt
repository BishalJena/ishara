package ai.ishara.demo.call

import ai.ishara.demo.call.ActiveCallViewModel.Delivery
import ai.ishara.demo.call.ActiveCallViewModel.EndReason
import ai.ishara.demo.call.ActiveCallViewModel.Phase
import ai.ishara.demo.core.call.AppMessage
import ai.ishara.demo.core.call.AskChoice
import ai.ishara.demo.core.call.AskOption
import ai.ishara.demo.core.call.Brief
import ai.ishara.demo.core.call.CallState
import ai.ishara.demo.core.call.DraftSource
import ai.ishara.demo.core.call.QuickReply
import ai.ishara.demo.core.call.ServerMessage
import ai.ishara.demo.core.call.Sign
import ai.ishara.demo.core.call.onMain
import ai.ishara.demo.models.CallSetup
import ai.ishara.demo.models.Delegation
import ai.ishara.demo.models.DraftBadge
import ai.ishara.demo.models.DraftDisplay
import ai.ishara.demo.models.label
import ai.ishara.demo.recognition.RecognitionEvent
import ai.ishara.demo.recognition.RecognitionResult
import ai.ishara.demo.support.RecordingDriver
import ai.ishara.demo.support.StubRecognition
import ai.ishara.demo.support.eventually
import androidx.test.ext.junit.runners.AndroidJUnit4
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The call screen's model over the real Swift `TurnStore` (ios/IsharaTests/ActiveCallViewModelTests.swift
 * and PickOneAndDelegatedTests.swift): what reaches the backend for each tap. The store's own
 * rules are covered in CallSession's tests; these check the model calls them as iOS does.
 */
@RunWith(AndroidJUnit4::class)
class ActiveCallFlowTest {
    private lateinit var driver: RecordingDriver
    private lateinit var model: ActiveCallViewModel

    @Before
    fun setUp() {
        place(CallSetup.demo)
    }

    @After
    fun tearDown() {
        onMain { driver.store.close() }
    }

    private fun place(setup: CallSetup) {
        driver = onMain { RecordingDriver() }
        model = onMain { ActiveCallViewModel(setup, driver, StubRecognition()) }
        runBlocking { withContext(Dispatchers.Main) { model.start() } }
        onMain { driver.store.receive(ServerMessage.Status(CallState.IN_CALL)) }
        assertTrue(eventually { model.phase == Phase.Live })
    }

    private fun sign(vararg signs: Sign) = onMain { signs.forEach { model.handle(RecognitionEvent.Result(RecognitionResult.Recognised(it))) } }

    /** A draft for the turn now on screen, once the store has shown it. */
    private fun draft(text: String, source: DraftSource = DraftSource.LLM) {
        val turn = onMain { driver.store.snapshot.value.currentTurnId }
        onMain { driver.store.receive(ServerMessage.Draft(turn, text, source)) }
        assertTrue(eventually { model.draft?.text == text })
    }

    private fun turnShown(): String = onMain { driver.store.snapshot.value.currentTurnId }

    @Test
    fun sendApprovesTheExactDraftForTheCurrentTurnOnce() {
        sign(Sign.HELLO, Sign.DOCTOR, Sign.TOMORROW)
        assertTrue(eventually { model.chips.size == 3 })
        val turn = turnShown()
        draft("Hello, I'd like a doctor's appointment tomorrow.")
        assertTrue(onMain { model.canSend })

        onMain { model.send() }
        onMain { model.send() }

        assertEquals(listOf(AppMessage.Approve(turn, "Hello, I'd like a doctor's appointment tomorrow.")), driver.approvals)
        assertTrue(eventually { model.delivery == Delivery.Speaking("Hello, I'd like a doctor's appointment tomorrow.") })
        assertTrue(onMain { model.chips.isEmpty() && model.draft == null && !model.canSend })
    }

    @Test
    fun unsureChipsAreNeverSentForRecomposing() {
        sign(Sign.YES)
        onMain { model.handle(RecognitionEvent.Result(RecognitionResult.Unsure)) }
        sign(Sign.THANKYOU)

        assertTrue(eventually { model.chips.map { it.label } == listOf("yes", "?", "thankyou") })
        assertEquals(listOf(listOf(Sign.YES), listOf(Sign.YES, Sign.THANKYOU)), driver.chipUpdates.map { it.chips })
    }

    @Test
    fun removingAChipRecomposesWithTheRemainingWords() {
        sign(Sign.NO, Sign.AFTERNOON, Sign.MORNING)
        assertTrue(eventually { model.chips.size == 3 })

        onMain { model.removeChip(model.chips.first { it.sign == Sign.AFTERNOON }) }

        assertTrue(eventually { model.chips.mapNotNull { it.sign } == listOf(Sign.NO, Sign.MORNING) })
        assertEquals(listOf(Sign.NO, Sign.MORNING), driver.chipUpdates.last().chips)
        assertEquals(4, driver.chipUpdates.size)
    }

    @Test
    fun notDeliveredOffersAResendOnANewTurnOnlyWhenTapped() {
        sign(Sign.NO)
        draft("No.")
        val first = turnShown()
        onMain { model.send() }
        assertTrue(eventually { model.isSpeaking })

        onMain { driver.store.receive(ServerMessage.NotDelivered(first, "no_confirmation")) }

        assertTrue(eventually { model.delivery == Delivery.NotDelivered("No.") })
        assertEquals(DraftDisplay("No.", DraftBadge.NOT_DELIVERED), onMain { model.draft })
        assertEquals("must never resend by itself", 1, driver.approvals.size)
        onMain { model.send() }
        assertEquals(2, driver.approvals.size)
        assertEquals("No.", driver.approvals.last().text)
        assertTrue("a resend goes out on a new turn", driver.approvals.last().turnId != first)
    }

    @Test
    fun stopAsksOnceWhileSpeakingAndAStoppedReplyIsOfferedAgain() {
        onMain { model.choose(QuickReply.YES) }
        assertTrue(eventually { model.draft == DraftDisplay("Yes.", DraftBadge.QUICK_REPLY) })
        val turn = turnShown()
        onMain { model.send() }
        assertTrue(eventually { model.isSpeaking })

        onMain {
            model.stop()
            model.stop()
        }
        assertEquals(1, driver.sent.count { it == AppMessage.Stop })
        onMain { driver.store.receive(ServerMessage.NotDelivered(turn, "stopped")) }

        assertTrue(eventually { model.delivery == Delivery.Stopped("Yes.") })
        assertEquals(DraftDisplay("Yes.", DraftBadge.STOPPED), onMain { model.draft })
        assertEquals(1, driver.approvals.size)
    }

    @Test
    fun quickRepliesInsertExactSentencesAndNeverSendByThemselves() {
        val expected = mapOf(
            QuickReply.YES to "Yes.",
            QuickReply.NO to "No.",
            QuickReply.WAIT to "Please wait a moment, I'm signing my reply.",
            QuickReply.REPEAT to "Sorry, could you please repeat that?",
        )
        for ((reply, sentence) in expected) {
            onMain { model.choose(reply) }
            assertTrue("$reply", eventually { model.draft == DraftDisplay(sentence, DraftBadge.QUICK_REPLY) })
        }
        assertTrue(driver.approvals.isEmpty())
    }

    @Test
    fun endSendsEndOnceAndNothingAfterIt() {
        sign(Sign.HELLO)
        draft("Hello.")

        onMain { model.end() }
        assertTrue(eventually { model.phase == Phase.Ended(EndReason.UserEnded) && model.chips.isEmpty() && model.draft == null })
        val atEnd = driver.sent.toList()
        assertEquals(1, atEnd.count { it == AppMessage.End })

        onMain {
            model.choose(QuickReply.YES)
            model.send()
            model.end()
            model.handle(RecognitionEvent.Result(RecognitionResult.Recognised(Sign.DOCTOR)))
            driver.store.receive(ServerMessage.Status(CallState.IN_CALL))
            driver.store.receive(ServerMessage.Caption("Hello?", 2.0))
        }

        assertEquals(atEnd, driver.sent.toList())
        assertFalse(onMain { model.canSend })
        assertTrue(eventually { model.captions.none { it.text == "Hello?" } && model.phase == Phase.Ended(EndReason.UserEnded) })
    }

    @Test
    fun aFailedHangUpAfterEndIsShownAsUnconfirmed() {
        onMain { model.end() }
        onMain { driver.store.receive(ServerMessage.Error(ActiveCallViewModel.END_FAILED, "Could not reach Bolna to hang up.")) }

        assertTrue(eventually { model.phase == Phase.Ended(EndReason.HangUpUnconfirmed) })
        assertEquals(null, onMain { model.errorMessage })
    }

    // Pick-one and delegated (D9)

    private val question = ServerMessage.Ask(
        "a1",
        "We have 4 pm tomorrow. Does that work?",
        listOf(AskOption(AskChoice.YES, "Yes."), AskOption(AskChoice.NO, "No."), AskOption(AskChoice.WAIT, "One moment.")),
        "I'll call back.",
        10.0,
    )

    private fun placeDelegated() {
        onMain { driver.store.close() }
        place(CallSetup.demo.copy(delegation = Delegation(Brief("b1", "…", "book a doctor's appointment", emptyList()), attended = true)))
        onMain { driver.store.receive(question) }
        assertTrue(eventually { model.openQuestion != null })
    }

    @Test
    fun aTappedCandidateBecomesAChipOnlyThen() {
        onMain { model.handle(RecognitionEvent.Result(RecognitionResult.Candidate(Sign.TOMORROW))) }
        assertTrue("nothing reaches the backend until the user taps", driver.sent.isEmpty())

        onMain { model.acceptCandidate() }

        assertTrue(eventually { model.chips.map { it.label } == listOf("tomorrow") })
        assertEquals(listOf(listOf(Sign.TOMORROW)), driver.chipUpdates.map { it.chips })
    }

    @Test
    fun aSignedYesAnswersTheAgentsQuestion() {
        placeDelegated()

        onMain { model.handle(RecognitionEvent.Result(RecognitionResult.Recognised(Sign.YES))) }

        assertEquals(listOf<AppMessage>(AppMessage.Answer("a1", AskChoice.YES)), driver.sent.toList())
    }

    @Test
    fun aTappedCandidateNoAnswersTheAgentsQuestion() {
        placeDelegated()

        onMain { model.handle(RecognitionEvent.Result(RecognitionResult.Candidate(Sign.NO))) }
        assertTrue("a candidate alone answers nothing", driver.sent.isEmpty())
        onMain { model.acceptCandidate() }

        assertEquals(listOf<AppMessage>(AppMessage.Answer("a1", AskChoice.NO)), driver.sent.toList())
    }

    @Test
    fun aDelegatedCallNeverComposesChips() {
        placeDelegated()

        onMain {
            model.handle(RecognitionEvent.Result(RecognitionResult.Recognised(Sign.TOMORROW)))
            model.handle(RecognitionEvent.Result(RecognitionResult.Unsure))
        }

        assertTrue(driver.sent.isEmpty())
        Thread.sleep(100)
        assertTrue(onMain { model.chips.isEmpty() })
    }
}
