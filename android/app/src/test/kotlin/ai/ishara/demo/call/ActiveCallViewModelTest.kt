package ai.ishara.demo.call

import ai.ishara.demo.call.ActiveCallViewModel.Delivery
import ai.ishara.demo.call.ActiveCallViewModel.EndReason
import ai.ishara.demo.call.ActiveCallViewModel.Phase
import ai.ishara.demo.core.call.AskChoice
import ai.ishara.demo.core.call.AskOption
import ai.ishara.demo.core.call.Brief
import ai.ishara.demo.core.call.CallCommand
import ai.ishara.demo.core.call.CallCoreException
import ai.ishara.demo.core.call.CallMode
import ai.ishara.demo.core.call.CallSocketClose
import ai.ishara.demo.core.call.CallState
import ai.ishara.demo.core.call.Caption
import ai.ishara.demo.core.call.Chip
import ai.ishara.demo.core.call.ChipKind
import ai.ishara.demo.core.call.Draft
import ai.ishara.demo.core.call.OpenQuestion
import ai.ishara.demo.core.call.QuickReply
import ai.ishara.demo.core.call.SendingPhase
import ai.ishara.demo.core.call.ServerError
import ai.ishara.demo.core.call.Sign
import ai.ishara.demo.core.call.StopProgress
import ai.ishara.demo.models.CallRecord
import ai.ishara.demo.models.CallSetup
import ai.ishara.demo.models.Delegation
import ai.ishara.demo.models.DraftBadge
import ai.ishara.demo.models.DraftDisplay
import ai.ishara.demo.models.label
import ai.ishara.demo.recognition.CameraState
import ai.ishara.demo.recognition.RecognitionEvent
import ai.ishara.demo.recognition.RecognitionResult
import ai.ishara.demo.support.FakeStore
import ai.ishara.demo.support.StubDriver
import ai.ishara.demo.support.StubRecognition
import ai.ishara.demo.support.snapshot
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Mirrors the mapping half of ios/IsharaTests/ActiveCallViewModelTests.swift: how a store
 * snapshot becomes what the call screen shows, and which store action each tap runs. The SEND
 * rules themselves run in Swift and are tested on the device (`ActiveCallFlowTest`).
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ActiveCallViewModelTest {
    private val driver = StubDriver()
    private val store: FakeStore get() = driver.store
    private val recognition = StubRecognition()

    private fun test(block: suspend TestScope.() -> Unit) = runTest(UnconfinedTestDispatcher(), testBody = block)

    private suspend fun TestScope.placed(setup: CallSetup = CallSetup.demo): ActiveCallViewModel {
        val model = ActiveCallViewModel(setup, driver, recognition, backgroundScope, now = { 500.0 })
        model.start()
        return model
    }

    private fun delegated(attended: Boolean, mode: CallMode = CallMode.DELEGATED) = CallSetup.demo.copy(
        delegation = Delegation(Brief("b1", "…", "book a doctor's appointment", emptyList()), attended, mode),
    )

    // Starting

    @Test
    fun startPlacesTheCallForTheChosenSetupAndShowsItsSnapshot() = test {
        val model = placed()

        assertEquals(listOf(CallSetup.demo), driver.startedWith)
        assertSame(store, model.store)
        assertEquals(Phase.Live, model.phase)
        store.update { it.copy(state = CallState.RINGING) }
        assertEquals(Phase.Connecting(CallState.RINGING), model.phase)
    }

    @Test
    fun startFailuresEndWithTheReasonAndSendNothing() = test {
        val reasons = mapOf(
            CallCoreException(CallCoreException.Kind.FORBIDDEN, 403, "x") to "This contact isn't on the backend's allowed list.",
            CallCoreException(CallCoreException.Kind.UNAUTHORIZED, 401, "x") to "The app token was refused. Check the app configuration.",
            CallCoreException(CallCoreException.Kind.SERVER, 502, "x") to "The backend couldn't start the call (HTTP 502).",
            CallCoreException(CallCoreException.Kind.NOT_HTTP_RESPONSE, null, "x") to "The backend couldn't be reached.",
            CallCoreException(CallCoreException.Kind.TRANSPORT, null, "offline") to "The call couldn't start: offline",
        )
        for ((error, reason) in reasons) {
            val failing = StubDriver().apply { startError = error }
            val model = ActiveCallViewModel(CallSetup.demo, failing, StubRecognition(), backgroundScope)
            model.start()

            assertEquals(Phase.Ended(EndReason.Failed(reason)), model.phase)
            assertFalse(model.canSend)
            assertTrue(failing.store.commands.isEmpty())
        }
    }

    @Test
    fun endWhileTheCallIsBeingPlacedEndsItOncePlaced() = test {
        val model = ActiveCallViewModel(CallSetup.demo, driver, recognition, backgroundScope)

        model.end()
        assertEquals(Phase.Ended(EndReason.UserEnded), model.phase)
        model.start()

        assertEquals(listOf<CallCommand>(CallCommand.End), store.commands)
        assertEquals(Phase.Ended(EndReason.UserEnded), model.phase)
    }

    @Test
    fun endingWhileACallFailsToStartStaysUserEnded() = test {
        driver.startError = CallCoreException(CallCoreException.Kind.SERVER, 502, "x")
        val model = ActiveCallViewModel(CallSetup.demo, driver, recognition, backgroundScope)

        model.end()
        model.start()

        assertEquals(Phase.Ended(EndReason.UserEnded), model.phase)
    }

    @Test
    fun leaveClosesTheDriverAndStopsRecognitionAndSendsNothing() = test {
        val model = placed()

        model.leave()

        assertEquals(1, driver.closeCount)
        assertEquals(1, recognition.stopCount)
        assertTrue(store.commands.isEmpty())
    }

    // Recognition

    @Test
    fun recognisedSignBecomesAChipAndUnsureAQuestionMark() = test {
        val model = placed()

        model.handle(RecognitionEvent.Result(RecognitionResult.Recognised(Sign.HELLO)))
        model.handle(RecognitionEvent.Result(RecognitionResult.Unsure))

        assertEquals(listOf(ChipKind.Recognised(Sign.HELLO), ChipKind.Unsure), store.added)
    }

    @Test
    fun recognitionEventsReachTheScreenWhileTheCallRuns() = test {
        val model = ActiveCallViewModel(CallSetup.demo, driver, recognition, backgroundScope)
        val running = backgroundScope.launch { model.run() }

        recognition.emit(RecognitionEvent.Camera(CameraState.SIGNING))
        recognition.emit(RecognitionEvent.Result(RecognitionResult.Recognised(Sign.DOCTOR)))

        assertEquals(CameraState.SIGNING, model.cameraState)
        assertEquals(ChipKind.Recognised(Sign.DOCTOR), store.added.single())
        running.cancel()
    }

    @Test
    fun cameraEventsDriveThePill() = test {
        val model = placed()
        model.handle(RecognitionEvent.Camera(CameraState.CANT_SEE))
        assertEquals(CameraState.CANT_SEE, model.cameraState)
        model.handle(RecognitionEvent.Camera(CameraState.WATCHING))
        assertEquals(CameraState.WATCHING, model.cameraState)
    }

    @Test
    fun candidateIsOfferedButNeverAChipUntilTapped() = test {
        val model = placed()

        model.handle(RecognitionEvent.Result(RecognitionResult.Candidate(Sign.TOMORROW)))
        assertEquals(Sign.TOMORROW, model.candidate)
        assertTrue("nothing reaches the store until the user taps", store.commands.isEmpty())

        model.acceptCandidate()
        assertNull(model.candidate)
        assertEquals(listOf(ChipKind.Recognised(Sign.TOMORROW)), store.added)
    }

    @Test
    fun theNextSignOrADismissDropsTheCandidate() = test {
        val model = placed()
        model.handle(RecognitionEvent.Result(RecognitionResult.Candidate(Sign.TOMORROW)))
        model.dismissCandidate()
        assertNull(model.candidate)

        model.handle(RecognitionEvent.Result(RecognitionResult.Candidate(Sign.MORNING)))
        model.handle(RecognitionEvent.Result(RecognitionResult.Recognised(Sign.YES)))

        assertNull(model.candidate)
        assertEquals(listOf(ChipKind.Recognised(Sign.YES)), store.added)
    }

    @Test
    fun candidateGoesAwayWhenTheCallEnds() = test {
        val model = placed()
        model.handle(RecognitionEvent.Result(RecognitionResult.Candidate(Sign.TOMORROW)))

        model.end()
        model.acceptCandidate()

        assertNull(model.candidate)
        assertEquals(listOf<CallCommand>(CallCommand.End), store.commands)
    }

    @Test
    fun handLeavingTheFrameShowsTheHintAndAQuestionMarkUntilTheNextSign() = test {
        val model = placed()

        model.handle(RecognitionEvent.Result(RecognitionResult.HandLeftFrame))
        assertTrue(model.showsFramingHint)
        assertEquals(listOf(ChipKind.Unsure), store.added)

        model.handle(RecognitionEvent.Result(RecognitionResult.Recognised(Sign.NO)))
        assertFalse(model.showsFramingHint)
    }

    @Test
    fun signsAfterEndAreIgnored() = test {
        val model = placed()
        model.end()

        model.handle(RecognitionEvent.Result(RecognitionResult.Recognised(Sign.DOCTOR)))
        model.handle(RecognitionEvent.Camera(CameraState.SIGNING))

        assertEquals(listOf<CallCommand>(CallCommand.End), store.commands)
        assertEquals(CameraState.WATCHING, model.cameraState)
    }

    // Delegated (D9) and steer

    @Test
    fun delegatedCallNeverComposesChipsButASignedOptionAnswers() = test {
        val model = placed(delegated(attended = true))

        model.handle(RecognitionEvent.Result(RecognitionResult.Recognised(Sign.TOMORROW)))
        model.handle(RecognitionEvent.Result(RecognitionResult.Unsure))
        assertEquals(listOf<CallCommand>(CallCommand.AnswerIfAsked(Sign.TOMORROW)), store.commands)

        store.answersSigns = true
        model.handle(RecognitionEvent.Result(RecognitionResult.Recognised(Sign.YES)))
        assertEquals(CallCommand.AnswerIfAsked(Sign.YES), store.commands.last())
        assertTrue(store.commands.none { it is CallCommand.Add })
    }

    @Test
    fun aSignThatAnsweredTheQuestionNeverBecomesAChipOnALiveCall() = test {
        val model = placed()
        store.answersSigns = true

        model.handle(RecognitionEvent.Result(RecognitionResult.Recognised(Sign.YES)))

        assertEquals(listOf<CallCommand>(CallCommand.AnswerIfAsked(Sign.YES)), store.commands)
    }

    @Test
    fun unattendedCallIgnoresSigns() = test {
        val model = placed(delegated(attended = false))

        model.handle(RecognitionEvent.Result(RecognitionResult.Recognised(Sign.YES)))
        model.handle(RecognitionEvent.Result(RecognitionResult.Candidate(Sign.NO)))

        assertFalse(model.watchesSigns)
        assertNull(model.candidate)
        assertTrue(store.commands.isEmpty())
    }

    @Test
    fun aSignOnASteerCallStepsInBeforeItBecomesAChip() = test {
        val model = placed(delegated(attended = false, mode = CallMode.STEER))

        model.handle(RecognitionEvent.Result(RecognitionResult.Recognised(Sign.NO)))

        assertTrue(model.watchesSigns)
        assertEquals(CallCommand.StartComposing, store.commands[1])
        assertEquals(ChipKind.Recognised(Sign.NO), (store.commands[2] as CallCommand.Add).chip.kind)
    }

    @Test
    fun delegatedCallStartsWithItsBrief() = test {
        val model = placed(delegated(attended = true))

        assertTrue(model.isDelegated)
        val request = driver.startedWith.single().startRequest
        assertEquals(CallMode.DELEGATED, request.mode)
        assertEquals("b1", request.briefId)
        assertTrue(request.attended)
    }

    // SEND, quick replies, delivery

    @Test
    fun sendApprovesWhenTheStoreCanSendAndResendsOnlyARetry() = test {
        val model = placed()
        model.send()
        assertTrue("nothing to send", store.commands.isEmpty())

        store.update { it.copy(canSend = true, draft = Draft("Hello.", Draft.Origin.LLM)) }
        model.send()
        assertEquals(CallCommand.Send, store.commands.last())

        store.update {
            it.copy(canSend = false, draft = null, canResend = true, unspokenText = "Hello.", sending = SendingPhase.NotDelivered("Hello."))
        }
        model.send()
        assertEquals(CallCommand.Resend, store.commands.last())
    }

    @Test
    fun aRetryIsOfferedOnlyWhileNoNewReplyIsStarted() = test {
        val model = placed()
        store.update { it.copy(canResend = true, unspokenText = "No.", sending = SendingPhase.NotDelivered("No.")) }
        assertEquals("No.", model.retryText)
        assertEquals(DraftDisplay("No.", DraftBadge.NOT_DELIVERED), model.draft)
        assertTrue(model.canSend)

        store.update { it.copy(chips = listOf(Chip("c1", ChipKind.Recognised(Sign.MORNING))), recognisedSigns = listOf(Sign.MORNING)) }

        assertNull(model.retryText)
        assertNull(model.draft)
        assertFalse(model.canSend)
        model.send()
        assertTrue("old text is never resent over new chips", store.commands.isEmpty())
    }

    @Test
    fun aStoppedReplyIsOfferedAgainWithTheStoppedBadge() = test {
        val model = placed()
        store.update { it.copy(canResend = true, unspokenText = "Yes.", sending = SendingPhase.Stopped("Yes.")) }

        assertEquals(Delivery.Stopped("Yes."), model.delivery)
        assertEquals(DraftDisplay("Yes.", DraftBadge.STOPPED), model.draft)
    }

    @Test
    fun theDraftBadgeSaysWhoWroteIt() = test {
        val model = placed()
        val badges = Draft.Origin.entries.map { origin ->
            store.update { it.copy(draft = Draft("x", origin)) }
            model.draft?.badge
        }
        assertEquals(listOf(DraftBadge.LLM, DraftBadge.TEMPLATE, DraftBadge.QUICK_REPLY), badges)
    }

    @Test
    fun deliveryFollowsTheStoresSendingPhase() = test {
        val model = placed()
        val phases = listOf(
            SendingPhase.Idle to Delivery.Idle,
            SendingPhase.Speaking("turn1", "Hi.") to Delivery.Speaking("Hi."),
            SendingPhase.Delivered to Delivery.Delivered,
            SendingPhase.DeliveredDespiteStop to Delivery.DeliveredDespiteStop,
            SendingPhase.NotDelivered("Hi.") to Delivery.NotDelivered("Hi."),
            SendingPhase.Stopped("Hi.") to Delivery.Stopped("Hi."),
        )
        for ((sending, delivery) in phases) {
            store.update { it.copy(sending = sending) }
            assertEquals(delivery, model.delivery)
        }
    }

    @Test
    fun composingOnlyWhileRecognisedChipsWaitForTheirDraft() = test {
        val model = placed()
        assertFalse(model.isComposing)
        store.update { it.copy(chips = listOf(Chip.unsure())) }
        assertFalse("an unsure chip is never sent, so no draft is coming", model.isComposing)

        store.update { it.copy(recognisedSigns = listOf(Sign.NO)) }
        assertTrue(model.isComposing)

        store.update { it.copy(draft = Draft("No.", Draft.Origin.TEMPLATE)) }
        assertFalse(model.isComposing)
    }

    @Test
    fun deliveryResultShowsUntilTheNextReplyStarts() = test {
        val model = placed()
        store.update { it.copy(sending = SendingPhase.Delivered) }
        assertTrue(model.showsDeliveryResult)

        store.update { it.copy(chips = listOf(Chip("c1", ChipKind.Recognised(Sign.YES)))) }
        assertFalse(model.showsDeliveryResult)
    }

    @Test
    fun quickRepliesGoToTheStoreOnlyWhileLiveAndNotSpeaking() = test {
        val model = placed()
        model.choose(QuickReply.YES)
        assertEquals(CallCommand.UseQuickReply(QuickReply.YES), store.commands.single())

        store.update { it.copy(sending = SendingPhase.Speaking("turn1", "Yes.")) }
        model.choose(QuickReply.NO)
        store.update { it.copy(sending = SendingPhase.Idle, state = CallState.RINGING) }
        model.choose(QuickReply.NO)

        assertFalse(model.canUseQuickReplies)
        assertEquals(1, store.commands.size)
    }

    @Test
    fun stopClearRemoveAndAnswerGoStraightToTheStore() = test {
        val model = placed()
        val chip = Chip("c1", ChipKind.Recognised(Sign.NO))

        model.stop()
        model.clear()
        model.removeChip(chip)
        model.answer(AskChoice.WAIT)

        assertEquals(
            listOf(CallCommand.Stop, CallCommand.Clear, CallCommand.Remove("c1"), CallCommand.Answer(AskChoice.WAIT)),
            store.commands,
        )
    }

    @Test
    fun tooLateStopHasItsOwnBannerNotAnErrorMessage() = test {
        val model = placed()
        store.update {
            it.copy(stopProgress = StopProgress.TOO_LATE, lastError = ServerError("cannot_interrupt", "x"), sending = SendingPhase.Speaking("t", "Yes."))
        }

        assertTrue(model.isStopTooLate)
        assertTrue(model.isSpeaking)
        assertNull(model.errorMessage)
    }

    @Test
    fun backendErrorsBecomeShortMessages() = test {
        val model = placed()
        val expected = mapOf(
            "stale_turn" to "That reply was out of date, so it wasn't sent.",
            "already_approved" to "That reply was already sent.",
            "busy_speaking" to "Wait until the current reply has been spoken.",
            "call_not_live" to "The call isn't connected yet. Nothing was sent.",
            "call_ended" to "The call has ended. Nothing will be sent.",
            "bad_message" to "The backend didn't understand the app. Nothing was sent.",
            "brand_new_code" to "Something went wrong on the backend.",
        )
        for ((code, message) in expected) {
            store.update { it.copy(lastError = ServerError(code, "raw backend text")) }
            assertEquals(code, message, model.errorMessage)
        }
        assertTrue("errors never send anything", store.commands.isEmpty())
    }

    // Ending and connection

    @Test
    fun endShowsEndedAtOnceAndSendsEndOnce() = test {
        val model = placed()

        model.end()
        assertEquals("before the store's snapshot lands", Phase.Ended(EndReason.UserEnded), model.phase)
        store.update { it.copy(state = CallState.ENDED) }
        model.end()

        assertEquals(Phase.Ended(EndReason.UserEnded), model.phase)
        assertEquals(listOf<CallCommand>(CallCommand.End), store.commands)
        assertNull(model.errorMessage)
    }

    @Test
    fun failedHangUpAfterEndIsUnconfirmedButARemoteEndIsNot() = test {
        val model = placed()
        model.end()
        store.update { it.copy(state = CallState.ENDED, lastError = ServerError("end_failed", "x")) }
        assertEquals(Phase.Ended(EndReason.HangUpUnconfirmed), model.phase)
        assertNull(model.errorMessage)

        val remote = ActiveCallViewModel(CallSetup.demo, StubDriver(FakeStore(snapshot(CallState.ENDED).copy(lastError = ServerError("end_failed", "x")))), StubRecognition(), backgroundScope)
        remote.start()
        assertEquals(Phase.Ended(EndReason.RemoteEnded), remote.phase)
    }

    @Test
    fun lostConnectionKeepsEndAvailableUntilReconnectingStops() = test {
        val model = placed()
        store.update { it.copy(state = CallState.ERROR, notice = "Nothing will be sent") }

        assertEquals(Phase.Interrupted("Nothing will be sent"), model.phase)
        assertFalse(model.isEnded)
        assertFalse("a reconnect may still bring the call back", model.isCallOver)

        driver.onReconnectStopped?.invoke(ReconnectStop.AttemptsUsedUp)

        assertEquals(Phase.Disconnected("The connection couldn't be restored"), model.phase)
        assertTrue(model.isCallOver)
    }

    @Test
    fun refusedReconnectsSayWhy() = test {
        val reasons = mapOf(
            CallSocketClose.UNAUTHORIZED to "The backend refused the app token",
            CallSocketClose.UNKNOWN_CALL to "The backend no longer knows this call",
            CallSocketClose.REPLACED to "This call is now connected somewhere else",
            CallSocketClose.DROPPED to "The connection couldn't be restored",
        )
        val model = placed()
        store.update { it.copy(state = CallState.ERROR) }
        for ((close, reason) in reasons) {
            driver.onReconnectStopped?.invoke(ReconnectStop.Refused(close))
            assertEquals(Phase.Disconnected(reason), model.phase)
        }
    }

    // Stage

    @Test
    fun stageFollowsThePhaseAndTheSentenceBeingSpoken() = test {
        val model = placed()
        assertEquals(ActiveCallStage.Signing, ActiveCallStage.of(model))

        store.update { it.copy(sending = SendingPhase.Speaking("turn1", "No, sorry, 4 pm doesn't work.")) }
        assertEquals(ActiveCallStage.Speaking("No, sorry, 4 pm doesn't work."), ActiveCallStage.of(model))

        store.update { it.copy(state = CallState.ERROR, notice = "Nothing will be sent") }
        assertEquals(ActiveCallStage.ConnectionLost("Nothing will be sent", isReconnecting = true), ActiveCallStage.of(model))
        driver.onReconnectStopped?.invoke(ReconnectStop.AttemptsUsedUp)
        assertEquals(ActiveCallStage.ConnectionLost("The connection couldn't be restored", isReconnecting = false), ActiveCallStage.of(model))

        model.end()
        assertEquals(ActiveCallStage.Ended(EndReason.UserEnded), ActiveCallStage.of(model))
    }

    // Record

    @Test
    fun aCallIsRecordedOnlyOnceItIsOverWithItsCaptions() = test {
        val model = placed()
        val caption = Caption("We have 4 pm tomorrow.", 100.0, Caption.Speaker.RECEPTIONIST)
        store.update { it.copy(captions = listOf(caption)) }
        assertNull("recorded while the call is still on", model.record)

        store.update { it.copy(state = CallState.ENDED) }

        val record = model.record!!
        assertEquals(model.recordId, record.id)
        assertEquals(500.0, record.date, 0.0)
        assertEquals("City Clinic", record.contactName)
        assertEquals(CallMode.LIVE, record.mode)
        assertNull(record.notes)
        assertEquals(listOf(CallRecord.Line(CallRecord.Line.Speaker.RECEPTIONIST, "We have 4 pm tomorrow.", 100.0)), record.captions)
        assertEquals("the same call gives the same record", record, model.record)
    }

    @Test
    fun aCallThatWasNeverPlacedIsNotRecorded() = test {
        driver.startError = CallCoreException(CallCoreException.Kind.FORBIDDEN, 403, "x")
        val model = placed()

        assertTrue(model.isCallOver)
        assertNull(model.record)
    }

    @Test
    fun captionSpeakersAreKept() {
        val speakers = Caption.Speaker.entries.map { CallRecord.Line(Caption("x", 5.0, it)).speaker }
        assertEquals(CallRecord.Line.Speaker.entries, speakers)
    }

    @Test
    fun openQuestionAndSteerStateComeFromTheSnapshot() = test {
        val model = placed()
        val question = OpenQuestion("a1", "4 pm?", listOf(AskOption(AskChoice.YES, "Yes.")), "I'll call back.", 10.0, 1.0)
        store.update { it.copy(openQuestion = question, followUps = listOf("DOB?"), steppedIn = 2, isComposing = true) }

        assertEquals(question, model.openQuestion)
        assertEquals(listOf("DOB?"), model.followUps)
        assertEquals(2, model.steppedIn)
        assertTrue(model.isSteppingIn)
        assertEquals(listOf("?"), listOf(Chip.unsure()).map { it.label })
    }
}
