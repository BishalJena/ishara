package ai.ishara.demo.ui.steer

import ai.ishara.demo.call.ActiveCallViewModel
import ai.ishara.demo.call.ActiveCallViewModel.Phase
import ai.ishara.demo.core.call.Brief
import ai.ishara.demo.core.call.CallCoreException
import ai.ishara.demo.core.call.CallMode
import ai.ishara.demo.core.call.CallState
import ai.ishara.demo.core.call.Caption
import ai.ishara.demo.core.call.Proposal
import ai.ishara.demo.core.call.ProposalOrigin
import ai.ishara.demo.models.CallSetup
import ai.ishara.demo.models.Contact
import ai.ishara.demo.models.Delegation
import ai.ishara.demo.support.StubDriver
import ai.ishara.demo.support.StubRecognition
import ai.ishara.demo.ui.components.formatElapsed
import ai.ishara.demo.ui.components.initials
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** Mirrors ios/IsharaTests/SteerCallViewLogicTests.swift, plus the steer screen's words. */
class SteerLogicTest {
    private fun caption(text: String, speaker: Caption.Speaker) = Caption(text, 0.0, speaker)

    @Test
    fun aRunOfCoverLinesShowsAsItsLastLine() {
        val captions = listOf(
            caption("sure can i have your file number please", Caption.Speaker.RECEPTIONIST),
            caption("One moment, please.", Caption.Speaker.AGENT),
            caption("Bear with me a moment.", Caption.Speaker.AGENT),
            caption("Sorry for the wait, they're still replying.", Caption.Speaker.AGENT),
            caption("It's pp4471920.", Caption.Speaker.USER),
            caption("One moment, please.", Caption.Speaker.AGENT),
        )
        val rows = CoverLines.rows(captions)
        assertEquals(listOf(0, 3, 4, 5), rows.map { it.index })
        assertEquals(listOf(0, 2, 0, 0), rows.map { it.folded })
    }

    @Test
    fun aCoverLineFromTheReceptionistIsNotFolded() {
        val rows = CoverLines.rows(listOf(caption("One moment, please.", Caption.Speaker.RECEPTIONIST), caption("One moment, please.", Caption.Speaker.AGENT)))
        assertEquals(listOf(0, 1), rows.map { it.index })
    }

    @Test
    fun timesInWordsBecomeFacts() {
        assertEquals("we have 4 pm tomorrow does that work", CallFacts.digitsForSpokenTimes("we have four pm tomorrow does that work"))
        assertEquals("10:30 am on monday", CallFacts.digitsForSpokenTimes("ten thirty am on monday"))
        assertEquals("come at 11", CallFacts.digitsForSpokenTimes("come at eleven o'clock"))
        assertEquals("I have one question", CallFacts.digitsForSpokenTimes("I have one question"))
        val facts = CallFacts.extract(listOf("okay we have wednesday at eleven am does that work")).map { it.text }
        assertEquals(setOf("11 am", "wednesday"), facts.toSet())
    }

    @Test
    fun aClockTimeIsOneFactAndTheOfferInQuickReplies() {
        val facts = CallFacts.extract(listOf("Let me see. I have Thursday at 10:30 am."))
        assertEquals(listOf("10:30 am", "Thursday"), facts.map { it.text })
        assertEquals(listOf(CallFacts.Kind.CLOCK, CallFacts.Kind.CALENDAR), facts.map { it.kind })
        assertEquals("Yes, 10:30 am works", QuickSteerReply.suggestions("Let me see. I have Thursday at 10:30 am.").first())
    }

    @Test
    fun amountsAreFactsButNeverOffers() {
        assertEquals(listOf("₹500"), CallFacts.extract(listOf("The fee is ₹500.")).map { it.text })
        assertEquals(listOf("Yes", "No", "Could you repeat that?", "One moment, please"), QuickSteerReply.suggestions("The fee is ₹500, is that fine?"))
        assertEquals(listOf("Could you repeat that?", "One moment, please"), QuickSteerReply.suggestions(null))
    }

    @Test
    fun onlyTheLastSixFactsAreKept() {
        val days = listOf("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
        assertEquals(days.drop(1), CallFacts.extract(days).map { it.text })
    }

    @Test
    fun aNumberShowsSpacedWithAPersonGlyph() {
        assertEquals("+91 98000 12345", Contact.display("+919800012345"))
        assertEquals("+91 98000 12345", Contact.indian("9800012345")?.name)
        assertEquals("Dr Mehta", Contact.indian("9800012345", name = "Dr Mehta")?.name)
        assertEquals("", initials("+91 98000 12345"))
        assertEquals("CC", initials("City Clinic"))
        assertEquals("DM", initials("Dr. Mehta's office"))
    }

    @Test
    fun theProposalBarCountsDownItsWindow() {
        val agent = Proposal("t1", "Yes, 10:30 works.", windowS = 2.0, origin = ProposalOrigin.AGENT, shownAt = 100.0)
        assertEquals("Ishara says in 2 s · tap to edit", SteerCallText.proposalLabel(agent, 100.0))
        assertEquals("Ishara says in 1 s · tap to edit", SteerCallText.proposalLabel(agent, 101.2))
        assertEquals("Ishara says in 0 s · tap to edit", SteerCallText.proposalLabel(agent, 105.0))
        assertEquals(0.5, agent.progress(101.0), 1e-9)
        assertEquals(1.0, agent.progress(110.0), 0.0)
        assertEquals(0.0, agent.progress(90.0), 0.0)
        assertEquals("Saying your line · tap to edit", SteerCallText.proposalLabel(agent.copy(origin = ProposalOrigin.USER), 100.0))
    }

    @Test
    fun theTimerShowsOnlyWhileConnected() {
        assertEquals("01:12 · from Ishara's number", SteerCallText.timer(100.0, Phase.Live, 172.5))
        assertEquals("Calls come from Ishara's number", SteerCallText.timer(null, Phase.Live, 172.5))
        assertEquals("Calls come from Ishara's number", SteerCallText.timer(100.0, Phase.Connecting(CallState.RINGING), 172.5))
        assertEquals("1:42", formatElapsed(0.0, 102.0))
    }

    private val steer = CallSetup.demo.copy(
        delegation = Delegation(Brief("b1", "…", "book a doctor's appointment", emptyList()), attended = false, mode = CallMode.STEER),
    )

    private suspend fun TestScope.steerCall(driver: StubDriver = StubDriver()) =
        ActiveCallViewModel(steer, driver, StubRecognition(), backgroundScope).also { it.start() }

    @Test
    fun statusSaysWhoIsDriving() = runTest(UnconfinedTestDispatcher()) {
        val driver = StubDriver()
        val model = steerCall(driver)
        assertEquals("Ishara is handling it — step in any time", SteerCallText.status(model, isSigning = false))

        driver.store.update { it.copy(isComposing = true) }
        assertEquals("You're typing — Ishara is covering", SteerCallText.status(model, isSigning = false))
        assertEquals("You're signing — Ishara waits for you", SteerCallText.status(model, isSigning = true))

        driver.store.update { it.copy(state = CallState.RINGING) }
        assertEquals("Ringing…", SteerCallText.status(model, isSigning = false))
        driver.store.update { it.copy(state = CallState.DIALING) }
        assertEquals("Calling…", SteerCallText.status(model, isSigning = false))
        driver.store.update { it.copy(state = CallState.ENDED) }
        assertEquals("Call ended", SteerCallText.status(model, isSigning = false))
    }

    @Test
    fun aCallThatNobodyAnsweredDidNotGetThrough() = runTest(UnconfinedTestDispatcher()) {
        val driver = StubDriver()
        val model = steerCall(driver)
        assertNull(SteerCallText.notThrough(model))

        driver.store.update { it.copy(state = CallState.ENDED, captions = listOf(caption("Hello, I'm calling for…", Caption.Speaker.AGENT))) }
        assertEquals("City Clinic didn't answer.", SteerCallText.notThrough(model))

        driver.store.update { it.copy(captions = it.captions + caption("City Clinic, hello?", Caption.Speaker.RECEPTIONIST)) }
        assertNull(SteerCallText.notThrough(model))
    }

    @Test
    fun aCallThatNeverStartedOrThatTheUserEndedEarly() = runTest(UnconfinedTestDispatcher()) {
        val failing = StubDriver().apply { startError = CallCoreException(CallCoreException.Kind.FORBIDDEN, 403, "x") }
        assertEquals("This contact isn't on the backend's allowed list.", SteerCallText.notThrough(steerCall(failing)))

        val ended = steerCall()
        ended.end()
        assertNull("the user hung up; it got through as far as they wanted", SteerCallText.notThrough(ended))
    }
}
