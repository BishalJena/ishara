package ai.ishara.demo.call

import ai.ishara.demo.call.ActiveCallViewModel.Delivery
import ai.ishara.demo.call.ActiveCallViewModel.EndReason
import ai.ishara.demo.call.ActiveCallViewModel.Phase
import ai.ishara.demo.core.call.AskChoice
import ai.ishara.demo.core.call.BriefRequest
import ai.ishara.demo.core.call.CallMode
import ai.ishara.demo.core.call.CallNotes
import ai.ishara.demo.core.call.CallPurpose
import ai.ishara.demo.core.call.Caption
import ai.ishara.demo.core.call.Chip
import ai.ishara.demo.core.call.CallStore
import ai.ishara.demo.core.call.Profile
import ai.ishara.demo.core.call.Sign
import ai.ishara.demo.core.call.onMain
import ai.ishara.demo.models.CallSetup
import ai.ishara.demo.models.Delegation
import ai.ishara.demo.models.DraftBadge
import ai.ishara.demo.models.label
import ai.ishara.demo.recognition.RecognitionController
import ai.ishara.demo.recognition.RecognitionEvent
import ai.ishara.demo.recognition.RecognitionResult
import ai.ishara.demo.recognition.ScriptedRecognitionController
import ai.ishara.demo.support.StubRecognition
import ai.ishara.demo.support.eventually
import ai.ishara.demo.support.launchOnMain
import androidx.test.ext.junit.runners.AndroidJUnit4
import kotlinx.coroutines.Job
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Mirrors ios/IsharaTests/FakeCallTests.swift: the fake demo call against the real Swift
 * `TurnStore`, so the SEND rules it shows are the shared ones. Runs fast on the device.
 */
@RunWith(AndroidJUnit4::class)
class FakeCallTest {
    private val fast = 0.02
    private val running = mutableListOf<Job>()
    private val models = mutableListOf<ActiveCallViewModel>()

    @After
    fun tearDown() {
        running.forEach(Job::cancel)
        onMain { models.forEach(ActiveCallViewModel::leave) }
    }

    private fun call(setup: CallSetup, driver: FakeCallDriver, recognition: RecognitionController = StubRecognition()): ActiveCallViewModel {
        val model = onMain { ActiveCallViewModel(setup, driver, recognition) }
        models += model
        running += launchOnMain { model.run() }
        return model
    }

    private fun delegatedSetup(attended: Boolean): CallSetup {
        val request = BriefRequest(CallPurpose.DOCTOR_APPOINTMENT, listOf(Sign.TOMORROW, Sign.MORNING), Profile(name = "Riya"))
        return CallSetup.demo.copy(delegation = Delegation(DelegatedDemo.brief(request), attended))
    }

    /** The driver's state belongs to the main thread, like the store's. */
    private fun notes(driver: FakeCallDriver): CallNotes = runBlocking { withContext(Dispatchers.Main) { driver.notes() } }

    @Test
    fun theWholeClinicScriptPlaysThroughTheRealTurnRules() {
        val recognition = onMain { ScriptedRecognitionController(timeScale = fast) }
        val driver = FakeCallDriver(FakeCallDriver.Options(timeScale = fast, undeliveredStages = setOf(1)), recognition = recognition)
        val model = call(CallSetup.demo, driver, recognition)

        // Turn 1: hello · doctor · tomorrow → LLM draft → SEND → delivered.
        assertTrue(eventually { model.draft?.text == "Hello, I'd like a doctor's appointment tomorrow." })
        assertEquals("the call opens with the agent's disclosure", Caption.Speaker.AGENT, onMain { model.captions.first().speaker })
        assertEquals(DemoScript.DISCLOSURE, onMain { model.captions.first().text })
        onMain { model.send() }
        assertTrue(eventually { model.delivery == Delivery.Delivered })

        // Turns 2–3b: the planned wrong chip is removed, then the reply isn't delivered once.
        assertTrue(eventually { model.chips.mapNotNull(Chip::sign) == listOf(Sign.NO, Sign.AFTERNOON, Sign.MORNING) })
        assertEquals("We have 4 pm tomorrow. Does that work?", onMain { model.captions.last().text })
        onMain { model.removeChip(model.chips.first { it.sign == Sign.AFTERNOON }) }
        assertTrue(eventually { model.draft?.badge == DraftBadge.LLM })
        onMain { model.send() }
        assertTrue(eventually { model.delivery == Delivery.NotDelivered("No, sorry, 4 pm doesn't work. Is there anything tomorrow morning?") })
        onMain { model.send() }
        assertTrue(eventually { model.delivery == Delivery.Delivered })

        // Turns 4–5: the unsure sign shows as [?] and is never part of the draft.
        assertTrue(eventually { model.chips.map { it.label } == listOf("yes", "?", "thankyou") })
        assertTrue(eventually { model.draft?.text == "Yes, 10:30 tomorrow morning works. Thank you." })
        onMain { model.send() }
        assertTrue(eventually { model.delivery == Delivery.Delivered })

        assertEquals(
            listOf(
                "Hello, I'd like a doctor's appointment tomorrow.",
                "No, sorry, 4 pm doesn't work. Is there anything tomorrow morning?",
                "Yes, 10:30 tomorrow morning works. Thank you.",
            ),
            onMain { model.captions.filter { it.speaker == Caption.Speaker.USER }.map { it.text } },
        )
        onMain { model.end() }
        assertEquals(Phase.Ended(EndReason.UserEnded), onMain { model.phase })
        // The goodbye goes in while End is still on its way (the driver is the store's synchronous sink).
        assertTrue(eventually { model.captions.lastOrNull()?.text == DemoScript.GOODBYE })
        assertEquals(Caption.Speaker.AGENT, onMain { model.captions.last().speaker })
        assertEquals("only the disclosure and the goodbye", 2, onMain { model.captions.count { it.speaker == Caption.Speaker.AGENT } })
    }

    /** Like the backend (`draft_is_current`), the fake never sends a draft for chips that have since changed. */
    @Test
    fun aDraftForChipsThatHaveSinceChangedIsNeverShown() {
        // Drafts come 1 s after their chips; the chips change again halfway through.
        val driver = FakeCallDriver(FakeCallDriver.Options(timeScale = 2.0))
        val store: CallStore = runBlocking { withContext(Dispatchers.Main) { driver.start(CallSetup.demo) } }
        try {
            val current = "Hello, I'd like a doctor's appointment tomorrow."
            onMain {
                store.add(Chip.recognised(Sign.HELLO))
                store.add(Chip.recognised(Sign.DOCTOR))
            }
            Thread.sleep(500)
            onMain { store.add(Chip.recognised(Sign.TOMORROW)) }

            // The drafts for the old chips were due at 1 s, the current one at 1.5 s.
            Thread.sleep(750)
            val shown = store.snapshot.value.draft?.text
            assertTrue("a draft for the old chips was shown: $shown", shown == null || shown == current)
            assertTrue(eventually { store.snapshot.value.draft?.text == current })
        } finally {
            onMain { driver.close() }
        }
    }

    // Delegated call (D9)

    @Test
    fun attendedDelegatedCallAsksThenBooksOnYes() {
        val driver = FakeCallDriver(FakeCallDriver.Options(timeScale = fast))
        val model = call(delegatedSetup(attended = true), driver)

        assertTrue(eventually { model.openQuestion != null })
        assertEquals(DelegatedDemo.OFFER, onMain { model.openQuestion?.question })
        assertEquals(
            listOf(DemoScript.DISCLOSURE, "I'd like to book a doctor's appointment for Riya, tomorrow in the morning."),
            onMain { model.captions.map { it.text }.take(2) },
        )

        onMain { model.handle(RecognitionEvent.Result(RecognitionResult.Recognised(Sign.YES))) }

        assertTrue(eventually { model.isEnded })
        assertNull(onMain { model.openQuestion })
        assertTrue("a delegated call never composes chips", onMain { model.chips.isEmpty() })
        val notes = notes(driver)
        assertTrue(notes.ready)
        assertEquals(CallMode.DELEGATED, notes.mode)
        assertEquals("booked", notes.outcome)
        assertTrue("You answered: \"Yes, 10:30 tomorrow works. Thank you.\"" in notes.summary)
        assertEquals(DelegatedDemo.CLOSE_LINE, notes.transcript.last().text)
    }

    @Test
    fun unattendedDelegatedCallPromisesACallbackAndNeverAsks() {
        val driver = FakeCallDriver(FakeCallDriver.Options(timeScale = fast))
        val model = call(delegatedSetup(attended = false), driver)

        assertTrue(eventually { model.isEnded })
        assertTrue(onMain { model.captions.any { it.text == DelegatedDemo.CALLBACK_LINE } })
        val notes = notes(driver)
        assertEquals("callback", notes.outcome)
        assertEquals(1, notes.openQuestions.size)
    }

    /** Like Bolna's final webhook: notes are ready when the call ends, its own summary a while later. */
    @Test
    fun bolnasSummaryReachesTheNotesOnlyAfterItsDelay() {
        val driver = FakeCallDriver(FakeCallDriver.Options(timeScale = fast, bolnaSummaryDelay = 30.0))
        val model = call(delegatedSetup(attended = false), driver)

        assertTrue(eventually { model.isEnded })
        val atEnd = notes(driver)
        assertTrue(atEnd.ready)
        assertNull("the summary came with the end of the call", atEnd.bolnaSummary)

        val deadline = System.currentTimeMillis() + 3_000
        while (notes(driver).bolnaSummary == null && System.currentTimeMillis() < deadline) Thread.sleep(20)
        val later = notes(driver)
        assertEquals("The agent called to book a doctor's appointment for Riya.", later.bolnaSummary)
        assertEquals("callback", later.outcome)
    }

    @Test
    fun unansweredQuestionTimesOutToTheCallbackLine() {
        val driver = FakeCallDriver(FakeCallDriver.Options(timeScale = fast))
        val model = call(delegatedSetup(attended = true), driver)

        assertTrue(eventually { model.isEnded })
        assertEquals("callback", notes(driver).outcome)
        assertTrue(onMain { model.captions.any { it.text == DelegatedDemo.CALLBACK_LINE } })
    }

    // Open "when?" question (version B)

    private val tomorrowLine = "Tomorrow, please. What times are available?"

    @Test
    fun openTimeQuestionIsAnsweredBySigningATimeWordThenTheOfferByYes() {
        val driver = FakeCallDriver(FakeCallDriver.Options(timeScale = fast, openTimeQuestion = FakeCallDriver.OpenTimeQuestion()))
        val model = call(delegatedSetup(attended = true), driver)

        assertTrue(eventually { model.openQuestion != null })
        val question = onMain { model.openQuestion }!!
        assertEquals(DelegatedDemo.OPEN_QUESTION, question.question)
        assertEquals(listOf(AskChoice.TOMORROW, AskChoice.MORNING, AskChoice.NOW, AskChoice.WAIT), question.options.map { it.choice })
        assertEquals(tomorrowLine, question.spoken(AskChoice.TOMORROW))
        assertEquals("Today, as soon as possible, please. What times are available?", question.spoken(AskChoice.NOW))

        onMain { model.handle(RecognitionEvent.Result(RecognitionResult.Recognised(Sign.YES))) } // no option here: answers nothing
        assertEquals(DelegatedDemo.OPEN_QUESTION, onMain { model.openQuestion?.question })
        onMain { model.handle(RecognitionEvent.Result(RecognitionResult.Recognised(Sign.TOMORROW))) }

        assertTrue(eventually { model.openQuestion?.question == DelegatedDemo.OFFER })
        assertTrue(onMain { model.captions.any { it.text == tomorrowLine && it.speaker == Caption.Speaker.USER } })
        onMain { model.handle(RecognitionEvent.Result(RecognitionResult.Recognised(Sign.YES))) }

        assertTrue(eventually { model.isEnded })
        val notes = notes(driver)
        assertEquals("booked", notes.outcome)
        assertTrue("You answered: \"$tomorrowLine\"" in notes.summary)
        assertTrue("You answered: \"Yes, 10:30 tomorrow works. Thank you.\"" in notes.summary)
    }

    /** `IsharaFakeOpenQuestion morning`: the scripted recognizer signs the answer. */
    @Test
    fun theFakeCallCanSignTheTimeWordItself() {
        val recognition = onMain { ScriptedRecognitionController(timeScale = fast) }
        val options = FakeCallDriver.Options(timeScale = fast, openTimeQuestion = FakeCallDriver.OpenTimeQuestion(signedAnswer = Sign.MORNING))
        val driver = FakeCallDriver(options, recognition = recognition)
        val model = call(delegatedSetup(attended = true), driver, recognition)

        assertTrue(eventually { model.openQuestion?.question == DelegatedDemo.OFFER })
        assertTrue(onMain { model.captions.any { it.text == "In the morning, please. What times are available?" } })
    }

    @Test
    fun unattendedOpenTimeQuestionIsAnsweredFromTheBriefThenACallback() {
        val driver = FakeCallDriver(FakeCallDriver.Options(timeScale = fast, openTimeQuestion = FakeCallDriver.OpenTimeQuestion()))
        val model = call(delegatedSetup(attended = false), driver)

        assertTrue(eventually { model.isEnded })
        assertNull(onMain { model.openQuestion })
        val agent = onMain { model.captions.filter { it.speaker == Caption.Speaker.AGENT }.map { it.text } }
        assertTrue("$agent", "Tomorrow in the morning, please. What times are available?" in agent)
        assertEquals("callback", notes(driver).outcome)
    }

    @Test
    fun theOpenTimeQuestionCanBeWordedLikeTheLiveTranscript() {
        val worded = "what time would will would you like to come in"
        val driver = FakeCallDriver(FakeCallDriver.Options(timeScale = fast, openTimeQuestion = FakeCallDriver.OpenTimeQuestion(question = worded)))
        val model = call(delegatedSetup(attended = true), driver)

        assertTrue(eventually { model.openQuestion != null })
        assertEquals(worded, onMain { model.openQuestion?.question })
        assertTrue(onMain { model.captions.any { it.text == worded && it.speaker == Caption.Speaker.RECEPTIONIST } })
    }

    @Test
    fun waitKeepsTheQuestionOpen() {
        val driver = FakeCallDriver(FakeCallDriver.Options(timeScale = fast))
        val model = call(delegatedSetup(attended = true), driver)
        assertTrue(eventually { model.openQuestion != null })

        onMain { model.answer(AskChoice.WAIT) }

        assertTrue(eventually { model.captions.lastOrNull()?.text == "One moment, please, I'm checking." })
        assertNotNull("wait holds the line; the question stays", onMain { model.openQuestion })
    }

    // Steer call

    @Test
    fun aSteerCallProposesLinesToAPresentUserAndBooks() {
        val brief = runBlocking { FakeCallDriver().createBrief(CallSetup.demo.copy(request = "Book a check-up").steerBriefRequest) }
        val setup = CallSetup.demo.copy(delegation = Delegation(brief, attended = false, mode = CallMode.STEER))
        // Slow enough that each 2 s proposal window (0.4 s here) is seen.
        val driver = FakeCallDriver(FakeCallDriver.Options(timeScale = 0.2))
        val model = call(setup, driver)
        assertTrue(eventually { model.store != null })
        onMain { model.setPresent(true) }

        assertTrue(eventually { model.proposal?.text == "No, 4 pm tomorrow doesn't work, sorry. Is there anything in the morning?" })
        assertTrue(eventually(10_000) { model.followUps == listOf("Can I get the date of birth?") })
        assertTrue(eventually(10_000) { model.isEnded })

        val notes = notes(driver)
        assertEquals(CallMode.STEER, notes.mode)
        assertEquals("booked", notes.outcome)
        assertEquals(listOf("Can I get the date of birth?"), notes.followUps)
    }

    @Test
    fun aTypedLineOnASteerCallIsPolishedPreviewedAndCountedAsSteppingIn() {
        val brief = runBlocking { FakeCallDriver().createBrief(CallSetup.demo.steerBriefRequest) }
        val setup = CallSetup.demo.copy(delegation = Delegation(brief, attended = false, mode = CallMode.STEER))
        val driver = FakeCallDriver(FakeCallDriver.Options(timeScale = 0.2))
        val model = call(setup, driver)
        assertTrue(eventually { model.store != null })
        onMain { model.setPresent(true) }

        onMain { model.say("can i come at nine") }

        assertTrue(eventually { model.proposal?.text == "Can i come at nine?" })
        assertTrue(eventually { model.captions.any { it.speaker == Caption.Speaker.USER && it.text == "Can i come at nine?" } })
        assertEquals(1, notes(driver).steppedIn)
    }
}
