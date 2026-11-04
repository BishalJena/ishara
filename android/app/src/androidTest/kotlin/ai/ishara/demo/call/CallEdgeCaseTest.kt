package ai.ishara.demo.call

import ai.ishara.demo.call.ActiveCallViewModel.Delivery
import ai.ishara.demo.call.ActiveCallViewModel.Phase
import ai.ishara.demo.core.call.AskChoice
import ai.ishara.demo.core.call.BriefRequest
import ai.ishara.demo.core.call.CallPurpose
import ai.ishara.demo.core.call.CallState
import ai.ishara.demo.core.call.Caption
import ai.ishara.demo.core.call.Profile
import ai.ishara.demo.core.call.ServerMessage
import ai.ishara.demo.core.call.Sign
import ai.ishara.demo.core.call.onMain
import ai.ishara.demo.models.CallSetup
import ai.ishara.demo.models.Delegation
import ai.ishara.demo.recognition.RecognitionEvent
import ai.ishara.demo.recognition.RecognitionResult
import ai.ishara.demo.recognition.ScriptedRecognitionController
import ai.ishara.demo.support.RecordingDriver
import ai.ishara.demo.support.StubRecognition
import ai.ishara.demo.support.eventually
import ai.ishara.demo.support.launchOnMain
import ai.ishara.demo.ui.notes.NotesModel
import androidx.test.ext.junit.runners.AndroidJUnit4
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Mirrors ios/IsharaTests/CallEdgeCaseTests.swift: a lost connection mid-call (live and
 * delegated) and a receptionist talking over the reply, against the real Swift `TurnStore`.
 */
@RunWith(AndroidJUnit4::class)
class CallEdgeCaseTest {
    /** Fast, but slow enough that a state lasting one script step is still seen by `eventually`. */
    private val fast = 0.05
    private val turn1 = "Hello, I'd like a doctor's appointment tomorrow."
    private val running = mutableListOf<Job>()
    private val models = mutableListOf<ActiveCallViewModel>()

    @After
    fun tearDown() {
        running.forEach(Job::cancel)
        onMain { models.forEach(ActiveCallViewModel::leave) }
    }

    private fun delegatedSetup(): CallSetup {
        val request = BriefRequest(CallPurpose.DOCTOR_APPOINTMENT, listOf(Sign.TOMORROW, Sign.MORNING), Profile(name = "Riya"))
        return CallSetup.demo.copy(delegation = Delegation(DelegatedDemo.brief(request), attended = true))
    }

    private fun run(model: ActiveCallViewModel): ActiveCallViewModel {
        models += model
        running += launchOnMain { model.run() }
        return model
    }

    /**
     * Regression: the agent's question stayed on screen and answerable after the connection
     * dropped, so a tap went into a dead socket.
     */
    @Test
    fun lostConnectionWipesTheAgentsQuestion() {
        val driver = onMain { RecordingDriver() }
        val model = run(onMain { ActiveCallViewModel(delegatedSetup(), driver, StubRecognition()) })
        assertTrue(eventually { model.store != null })
        onMain {
            driver.store.receive(ServerMessage.Status(CallState.IN_CALL))
            driver.store.receive(ServerMessage.Ask("a1", DelegatedDemo.OFFER, DelegatedDemo.options, DelegatedDemo.CALLBACK_LINE, 10.0))
        }
        assertTrue(eventually { model.openQuestion != null })

        onMain { driver.store.connectionLost() }

        assertTrue("the question outlived the connection", eventually { model.openQuestion == null })
        onMain {
            model.answer(AskChoice.YES)
            model.handle(RecognitionEvent.Result(RecognitionResult.Recognised(Sign.YES)))
        }
        assertTrue("an answer went out with the connection gone", driver.sent.isEmpty())
    }

    @Test
    fun fakeConnectionThatStaysDownEndsReconnectingAndFailsTheNotes() {
        val driver = FakeCallDriver(FakeCallDriver.Options(timeScale = fast, connectionDrop = FakeCallDriver.ConnectionDrop.STAYS_DOWN))
        val model = run(onMain { ActiveCallViewModel(delegatedSetup(), driver, StubRecognition()) })

        assertTrue(eventually { model.openQuestion != null })
        assertTrue(eventually { model.phase == Phase.Interrupted(ActiveCallViewModel.DISCONNECTED_NOTICE) })
        assertNull(onMain { model.openQuestion })
        assertTrue(eventually { model.reconnectStop == ReconnectStop.AttemptsUsedUp })
        assertTrue(onMain { model.isCallOver })

        onMain { model.leave() }
        val notes = onMain { NotesModel("City Clinic", driver) }
        runBlocking { withContext(Dispatchers.Main) { notes.refresh() } }
        assertNull(onMain { notes.notes })
        assertEquals("The notes couldn't be loaded: Could not connect to the server.", onMain { notes.failure })
    }

    @Test
    fun fakeDropWipesTheDraftAndTheReconnectResendsNothing() {
        val recognition = onMain { ScriptedRecognitionController(timeScale = fast) }
        val driver = FakeCallDriver(FakeCallDriver.Options(timeScale = fast, connectionDrop = FakeCallDriver.ConnectionDrop.RECONNECTS), recognition = recognition)
        val model = run(onMain { ActiveCallViewModel(CallSetup.demo, driver, recognition) })

        assertTrue(eventually { model.draft?.text == turn1 })
        assertTrue(eventually { model.phase == Phase.Interrupted(ActiveCallViewModel.DISCONNECTED_NOTICE) })
        assertNull(onMain { model.draft })
        assertTrue(onMain { model.chips.isEmpty() })
        assertFalse(onMain { model.canSend })
        onMain { model.send() }

        assertTrue(eventually { model.phase == Phase.Live })
        assertNull("the old draft came back with the connection", onMain { model.draft })
        assertFalse(onMain { model.canSend })
        assertEquals("something was sent across the drop", Delivery.Idle, onMain { model.delivery })
        assertFalse(onMain { model.captions.any { it.speaker == Caption.Speaker.USER } })
    }

    @Test
    fun receptionistTalkingOverTheReplyKeepsItSpeakingAndDelivers() {
        val recognition = onMain { ScriptedRecognitionController(timeScale = fast) }
        val driver = FakeCallDriver(FakeCallDriver.Options(timeScale = fast, interruptedStages = setOf(0)), recognition = recognition)
        val model = run(onMain { ActiveCallViewModel(CallSetup.demo, driver, recognition) })

        assertTrue(eventually { model.draft?.text == turn1 })
        onMain { model.send() }

        assertTrue(eventually { model.captions.lastOrNull()?.text == FakeCallDriver.INTERRUPTION })
        assertEquals("the receptionist's words cut the reply off", Delivery.Speaking(turn1), onMain { model.delivery })
        assertTrue(eventually { model.delivery == Delivery.Delivered })
        assertEquals(listOf(turn1), onMain { model.captions.filter { it.speaker == Caption.Speaker.USER }.map { it.text } })
    }
}
