package ai.ishara.demo.ui

import ai.ishara.demo.call.ActiveCallViewModel
import ai.ishara.demo.call.CallFollowUp
import ai.ishara.demo.call.DelegatedDemo
import ai.ishara.demo.core.call.BriefRequest
import ai.ishara.demo.core.call.CallCoreException
import ai.ishara.demo.core.call.CallMode
import ai.ishara.demo.core.call.CallNotes
import ai.ishara.demo.core.call.CallPurpose
import ai.ishara.demo.core.call.CallState
import ai.ishara.demo.core.call.Profile
import ai.ishara.demo.core.call.ProtocolLimits
import ai.ishara.demo.core.call.Sign
import ai.ishara.demo.models.CallHistory
import ai.ishara.demo.models.CallSetup
import ai.ishara.demo.models.Contact
import ai.ishara.demo.models.Delegation
import ai.ishara.demo.recognition.RecognitionEvent
import ai.ishara.demo.recognition.RecognitionResult
import ai.ishara.demo.support.MainDispatcherRule
import ai.ishara.demo.support.StubDriver
import ai.ishara.demo.support.StubRecognition
import ai.ishara.demo.ui.classic.BriefModel
import ai.ishara.demo.ui.notes.NotesModel
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

/** Mirrors ios/IsharaTests/BriefAndNotesModelTests.swift and the follow-up half of CallRecordingTests.swift. */
@OptIn(ExperimentalCoroutinesApi::class)
class BriefAndNotesModelTest {
    @get:Rule
    val temporary = TemporaryFolder()

    @get:Rule
    val main = MainDispatcherRule()

    private val driver = StubDriver()
    private val brief = BriefModel(CallSetup.demo, driver, StubRecognition())

    private fun sign(result: RecognitionResult) = brief.handle(RecognitionEvent.Result(result))

    // Brief (D9 step 1)

    @Test
    fun signsBecomeChipsOnceEachUpToTheLimit() {
        sign(RecognitionResult.Recognised(Sign.TOMORROW))
        sign(RecognitionResult.Recognised(Sign.MORNING))
        sign(RecognitionResult.Recognised(Sign.TOMORROW))
        assertEquals(listOf(Sign.TOMORROW, Sign.MORNING), brief.chips)

        Sign.entries.forEach(brief::add)
        assertEquals(ProtocolLimits.MAX_CHIPS, brief.chips.size)
    }

    @Test
    fun unsureAndFramingAreExplainedNotAdded() {
        sign(RecognitionResult.Unsure)
        assertTrue(brief.lastSignUnsure)
        assertFalse(brief.showsFramingHint)

        sign(RecognitionResult.HandLeftFrame)
        assertTrue(brief.showsFramingHint)
        assertTrue(brief.chips.isEmpty())

        brief.add(Sign.TODAY)
        assertFalse(brief.lastSignUnsure)
    }

    @Test
    fun candidateNeedsATap() {
        sign(RecognitionResult.Candidate(Sign.TOMORROW))
        assertTrue(brief.chips.isEmpty())

        brief.acceptCandidate()

        assertEquals(listOf(Sign.TOMORROW), brief.chips)
        assertNull(brief.candidate)
    }

    @Test
    fun briefIsBuiltFromExactlyWhatIsOnScreen() = runTest {
        brief.add(Sign.TOMORROW)
        brief.callback = " +91 98 "
        brief.reason = ""

        brief.prepare()

        assertEquals(
            listOf(BriefRequest(CallPurpose.DOCTOR_APPOINTMENT, listOf(Sign.TOMORROW), Profile(name = "Riya", callback = "+91 98"))),
            driver.briefRequests,
        )
        assertEquals("b1", brief.brief?.briefId)
    }

    @Test
    fun editingAfterTheBriefHidesItUntilRebuilt() = runTest {
        brief.add(Sign.TOMORROW)
        brief.prepare()
        assertNotNull(brief.approvedSetup)

        brief.add(Sign.MORNING)
        assertNull("the shown brief no longer matches the chips", brief.brief)
        assertNull(brief.approvedSetup)

        brief.remove(Sign.MORNING)
        assertNotNull("back to what was approved", brief.brief)
    }

    @Test
    fun approvedSetupCarriesTheBriefAndTheChoice() = runTest {
        brief.name = "  Asha "
        brief.prepare()
        brief.attended = false

        val approved = brief.approvedSetup!!

        assertEquals("Asha", approved.details.name)
        assertEquals(Delegation(driver.briefResult.getOrThrow(), attended = false), approved.delegation)
        assertEquals(Contact.cityClinic, approved.contact)
    }

    @Test
    fun noNameNoBrief() = runTest {
        brief.name = "   "
        assertFalse(brief.canPrepare)

        brief.prepare()

        assertTrue(driver.briefRequests.isEmpty())
    }

    @Test
    fun backendRefusalIsExplained() = runTest {
        driver.briefResult = Result.failure(CallCoreException(CallCoreException.Kind.VALIDATION, 422, "x"))

        brief.prepare()

        assertNull(brief.brief)
        assertEquals("The backend didn't accept these details. Check the name and callback number.", brief.failure)
        assertFalse(brief.isPreparing)
    }

    // Notes (D9 last step)

    private fun notes(ready: Boolean, bolna: String? = null) =
        CallNotes(callId = "c1", mode = CallMode.DELEGATED, ready = ready, outcome = if (ready) "booked" else null, bolnaSummary = bolna)

    private fun TestScope.notesModel(sleep: suspend (kotlin.time.Duration) -> Unit = {}, onNotes: (CallNotes) -> Unit = {}) =
        NotesModel("City Clinic", driver, onNotes, sleep, backgroundScope)

    @Test
    fun keepsCheckingUntilTheCallEndedAndBolnasSummaryArrived() = runTest {
        driver.notesResults = mutableListOf(Result.success(notes(false)), Result.success(notes(true)), Result.success(notes(true, "Booked for 10:30.")))
        val model = notesModel()

        model.run()

        assertEquals(3, driver.notesCalls)
        assertEquals("Booked for 10:30.", model.notes?.bolnaSummary)
        assertTrue(model.isComplete)
    }

    @Test
    fun waitsThreeSecondsBetweenChecks() = runTest {
        val waits = mutableListOf<kotlin.time.Duration>()
        driver.notesResults = mutableListOf(Result.success(notes(false)), Result.success(notes(true, "x")))

        notesModel(sleep = { waits += it }).run()

        assertEquals(listOf(NotesModel.REFRESH_INTERVAL), waits)
        assertEquals(3_000, NotesModel.REFRESH_INTERVAL.inWholeMilliseconds)
    }

    @Test
    fun stopsAfterTheLastRefreshWithoutBolnasSummary() = runTest {
        driver.notesResults = mutableListOf(Result.success(notes(true)))

        notesModel().run()

        assertEquals(NotesModel.MAX_REFRESHES + 1, driver.notesCalls)
        assertEquals(11, driver.notesCalls)
    }

    @Test
    fun startPollsOnceHoweverOftenItIsAskedTo() = runTest(main.dispatcher) {
        driver.notesResults = mutableListOf(Result.success(notes(true)), Result.success(notes(true, "Booked for 10:30.")))
        val model = notesModel()

        val first = model.start()
        assertSame(first, model.start())
        first.join()
        model.start().join()

        assertEquals("a second loop polled the same call", 2, driver.notesCalls)
        assertTrue(model.isComplete)
    }

    @Test
    fun stopEndsThePolling() = runTest {
        driver.notesResults = mutableListOf(Result.success(notes(true)))
        val model = NotesModel("City Clinic", driver, scope = backgroundScope)

        val polling = model.start()
        runCurrent()
        assertEquals(1, driver.notesCalls)
        model.stop()
        advanceUntilIdle()

        assertTrue(polling.isCancelled)
        assertEquals(1, driver.notesCalls)
    }

    @Test
    fun aForgottenCallIsExplainedAndAFailedSleepEndsTheLoop() = runTest {
        driver.notesResults = mutableListOf(Result.failure(CallCoreException(CallCoreException.Kind.NOT_FOUND, 404, "x")))

        val model = notesModel(sleep = { throw IllegalStateException("no clock") })

        model.run()

        assertEquals("The backend no longer has this call (it may have restarted).", model.failure)
        assertEquals(1, driver.notesCalls)
    }

    @Test
    fun loadFailuresAreExplained() = runTest {
        val failures = mapOf(
            CallCoreException(CallCoreException.Kind.NOT_FOUND, 404, "x") to "The backend no longer has this call (it may have restarted).",
            CallCoreException(CallCoreException.Kind.SERVER, 500, "x") to "The notes couldn't be loaded (HTTP 500).",
            CallCoreException(CallCoreException.Kind.NOT_HTTP_RESPONSE, null, "x") to "The backend couldn't be reached.",
            IllegalStateException("offline") to "The notes couldn't be loaded: offline",
        )
        for ((error, message) in failures) {
            driver.notesResults = mutableListOf(Result.failure(error))
            val model = notesModel()
            model.refresh()
            assertEquals(message, model.failure)
            assertFalse(model.isLoading)
        }
    }

    @Test
    fun cancellingThePollingIsNotAFailure() = runTest {
        driver.notesResults = mutableListOf(Result.success(notes(true)))
        val model = notesModel(sleep = { throw CancellationException("left") })

        val outcome = runCatching { model.run() }

        assertTrue(outcome.exceptionOrNull() is CancellationException)
        assertNull(model.failure)
    }

    @Test
    fun outcomeWords() {
        assertEquals("Booked", NotesModel.describe("booked", ready = true))
        assertEquals("The agent will need to call back", NotesModel.describe("callback", ready = true))
        assertEquals("Nothing suitable was offered", NotesModel.describe("declined", ready = true))
        assertEquals("Nobody answered", NotesModel.describe("no_answer", ready = true))
        assertEquals("Finished", NotesModel.describe("done", ready = true))
        assertEquals("The call is still being wrapped up", NotesModel.describe(null, ready = false))
        assertEquals("Not confirmed: read the transcript", NotesModel.describe("unclear", ready = true))
    }

    // Follow-up after the call (CallRecordingTests)

    private fun delegatedSetup() = CallSetup.demo.copy(
        delegation = Delegation(
            DelegatedDemo.brief(BriefRequest(CallPurpose.DOCTOR_APPOINTMENT, listOf(Sign.TOMORROW), Profile(name = "Riya"))),
            attended = false,
        ),
    )

    private fun delegatedNotes(bolna: String? = null) =
        CallNotes(callId = "c1", mode = CallMode.DELEGATED, ready = true, outcome = "callback", bolnaSummary = bolna)

    private suspend fun TestScope.endedCall(setup: CallSetup): ActiveCallViewModel {
        val model = ActiveCallViewModel(setup, driver, StubRecognition(), backgroundScope)
        model.start()
        driver.store.update { it.copy(state = CallState.ENDED) }
        return model
    }

    @Test
    fun callForMeNotesAreFollowedAfterTheUserLeaves() = runTest(main.dispatcher) {
        val model = endedCall(delegatedSetup())
        driver.notesResults = mutableListOf(
            Result.success(delegatedNotes()), Result.success(delegatedNotes()), Result.success(delegatedNotes("The caller will be called back.")),
        )
        val folder = temporary.newFolder("CallHistory")
        val history = CallHistory(folder)

        val followed = CallFollowUp.callEnded(model, history, sleep = {})
        model.leave()
        advanceUntilIdle()

        val record = CallHistory(folder).records.single()
        assertEquals(model.recordId, record.id)
        assertEquals("The caller will be called back.", record.notes?.bolnaSummary)
        assertEquals(3, driver.notesCalls)
        // The notes screen shows this same follow-up; opening it doesn't poll again.
        followed!!.start().join()
        assertEquals(3, driver.notesCalls)
    }

    @Test
    fun theFollowUpGivesUpWhenTheTriesRunOut() = runTest(main.dispatcher) {
        val model = endedCall(delegatedSetup())
        driver.notesResults = mutableListOf(Result.success(delegatedNotes()))
        val history = CallHistory(folder = null)

        CallFollowUp.callEnded(model, history, sleep = {})
        advanceUntilIdle()

        assertEquals(NotesModel.MAX_REFRESHES + 1, driver.notesCalls)
        assertEquals("the notes it did get weren't saved", delegatedNotes(), history.records.single().notes)
    }

    @Test
    fun aLiveCallIsSavedButNotFollowed() = runTest(main.dispatcher) {
        val model = endedCall(CallSetup.demo)
        driver.notesResults = mutableListOf(Result.success(CallNotes(callId = "c1", mode = CallMode.LIVE, ready = true)))
        val history = CallHistory(folder = null)

        assertNull(CallFollowUp.callEnded(model, history, sleep = {}))
        advanceUntilIdle()

        assertEquals(listOf(model.recordId), history.records.map { it.id })
        assertEquals(0, driver.notesCalls)
    }

    @Test
    fun aCallThatWasNeverPlacedHasNoFollowUp() = runTest(main.dispatcher) {
        driver.startError = CallCoreException(CallCoreException.Kind.FORBIDDEN, 403, "x")
        val model = ActiveCallViewModel(delegatedSetup(), driver, StubRecognition(), backgroundScope)
        model.start()
        val history = CallHistory(folder = null)

        assertNull(CallFollowUp.callEnded(model, history, sleep = {}))
        assertTrue(history.records.isEmpty())
        assertEquals(0, driver.notesCalls)
    }

    @Test
    fun theNotesScreenHandsBolnasLateSummaryToTheSavedCall() = runTest(main.dispatcher) {
        val model = endedCall(CallSetup.demo)
        val folder = temporary.newFolder("Saved")
        val history = CallHistory(folder)
        val record = model.record!!
        history.save(record)
        driver.notesResults = mutableListOf(Result.success(delegatedNotes()), Result.success(delegatedNotes("Call back.")))

        notesModel(onNotes = { history.update(record.id, it) }).run()

        assertEquals(2, driver.notesCalls)
        val saved = CallHistory(folder).records.single()
        assertEquals("Call back.", saved.notes?.bolnaSummary)
        assertEquals(record.captions, saved.captions)
    }
}
