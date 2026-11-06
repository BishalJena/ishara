package ai.ishara.demo.app

import ai.ishara.demo.call.ActiveCallViewModel
import ai.ishara.demo.call.CallDriver
import ai.ishara.demo.call.CallDriverError
import ai.ishara.demo.call.DelegatedDemo
import ai.ishara.demo.call.DemoScript
import ai.ishara.demo.call.ReconnectStop
import ai.ishara.demo.core.call.Brief
import ai.ishara.demo.core.call.BriefRequest
import ai.ishara.demo.core.call.CallCore
import ai.ishara.demo.core.call.CallNotes
import ai.ishara.demo.core.call.CallState
import ai.ishara.demo.core.call.CallStore
import ai.ishara.demo.core.call.CaptionSpeaker
import ai.ishara.demo.core.call.Chip
import ai.ishara.demo.core.call.DraftSource
import ai.ishara.demo.core.call.LocalCallSession
import ai.ishara.demo.core.call.Profile
import ai.ishara.demo.core.call.ServerMessage
import ai.ishara.demo.core.call.Sign
import ai.ishara.demo.core.call.TranscriptEntry
import ai.ishara.demo.models.CallSetup
import ai.ishara.demo.recognition.CameraState
import ai.ishara.demo.recognition.RecognitionController
import ai.ishara.demo.recognition.RecognitionEvent
import ai.ishara.demo.recognition.ScriptedRecognitionController
import ai.ishara.demo.ui.notes.NotesModel
import ai.ishara.demo.core.call.CallPresentation
import kotlinx.coroutines.flow.first

/** Hands the view model a store prepared in advance; what the store sends is swallowed, so its state stays put. */
class FixtureCallDriver : CallDriver {
    val store: LocalCallSession = CallCore.startLocalSession(CallState.DIALING).also { it.sink = {} }

    /** What [notes] returns; without it, there was no call. */
    var fixedNotes: CallNotes? = null

    override var onReconnectStopped: ((ReconnectStop) -> Unit)? = null

    override suspend fun start(setup: CallSetup): CallStore = store

    override fun close() {
        store.close()
    }

    override suspend fun createBrief(request: BriefRequest): Brief = DelegatedDemo.brief(request)

    override suspend fun notes(): CallNotes = fixedNotes ?: throw CallDriverError.NoCall
}

/**
 * The Notes screen after the scripted delegated call was booked on a "yes", with an automatic
 * summary standing in for the one Bolna's webhook delivers. Main thread only.
 */
fun DemoFixture.makeNotes(): NotesModel? {
    if (this != DemoFixture.NOTES) return null
    val setup = CallSetup.demo
    val brief = DelegatedDemo.brief(
        BriefRequest(setup.purpose, listOf(Sign.TOMORROW, Sign.MORNING), Profile(name = setup.details.name)),
    )
    val answer = DelegatedDemo.options[0].spoken
    val now = System.currentTimeMillis() / 1000.0
    val transcript = listOf(
        TranscriptEntry(CaptionSpeaker.AGENT, DemoScript.DISCLOSURE, now),
        TranscriptEntry(CaptionSpeaker.RECEPTIONIST, DelegatedDemo.OFFER, now),
        TranscriptEntry(CaptionSpeaker.AGENT, answer, now),
        TranscriptEntry(CaptionSpeaker.RECEPTIONIST, DelegatedDemo.CONFIRMATION, now),
    )
    val notes = DelegatedDemo.notes(brief.goal, setup.details.name, brief.text, transcript, listOf(answer), ready = true)
        .copy(bolnaSummary = "The caller booked a doctor's appointment for 10:30 tomorrow morning.",
            presentation = CallPresentation(title = "Book a clinic appointment", overview = "The clinic confirmed the appointment.", keyPoints = listOf("Tomorrow morning at 10:30.")))
    val driver = FixtureCallDriver().apply { fixedNotes = notes }
    return NotesModel(contactName = setup.contact.name, driver = driver)
}

/**
 * Builds the call screen state by replaying PLAN §1 messages into a real TurnStore. Tests pass
 * a [recognition] with a stand-in camera. Main thread only.
 */
suspend fun DemoFixture.makeActiveCall(recognition: RecognitionController = ScriptedRecognitionController()): ActiveCallViewModel? {
    if (this == DemoFixture.HOME || this == DemoFixture.GET_READY || this == DemoFixture.NOTES) return null
    val driver = FixtureCallDriver()
    val store = driver.store
    val model = ActiveCallViewModel(CallSetup.demo, driver, recognition)
    model.attach(store)
    fun now() = System.currentTimeMillis() / 1000.0

    // Store actions apply at once; only a new turn id needs its snapshot before it is used.
    suspend fun sendAndAwaitNextTurn(): String {
        val sent = store.snapshot.value.currentTurnId
        store.send()
        store.snapshot.first { it.currentTurnId != sent }
        return sent
    }

    store.receive(ServerMessage.Status(CallState.IN_CALL))
    if (this == DemoFixture.ENDED_NO_CAPTIONS) {
        model.end()
        return model
    }
    store.receive(ServerMessage.Caption(DemoScript.DISCLOSURE, now(), CaptionSpeaker.AGENT))
    store.add(Chip.recognised(Sign.HELLO))
    store.receive(ServerMessage.Draft(store.snapshot.value.currentTurnId, "Hello, I'd like a doctor's appointment tomorrow.", DraftSource.LLM))
    val firstTurn = sendAndAwaitNextTurn()
    store.receive(ServerMessage.Spoken(firstTurn))
    store.receive(ServerMessage.Caption("We have 4 pm tomorrow. Does that work?", now()))

    val wrong = Chip.recognised(Sign.AFTERNOON)
    listOf(Chip.recognised(Sign.NO), wrong, Chip.recognised(Sign.MORNING), Chip.unsure()).forEach(store::add)
    val turn = store.snapshot.value.currentTurnId
    store.receive(ServerMessage.Draft(turn, "No. In the afternoon, please. In the morning, please.", DraftSource.TEMPLATE))
    model.handle(RecognitionEvent.Camera(CameraState.SIGNING))
    if (this == DemoFixture.SIGNING) return model

    store.remove(wrong)
    if (this == DemoFixture.COMPOSING) return model
    store.receive(ServerMessage.Draft(turn, "No, sorry, 4 pm doesn't work. Is there anything tomorrow morning?", DraftSource.LLM))
    model.handle(RecognitionEvent.Camera(CameraState.WATCHING))
    val secondTurn = sendAndAwaitNextTurn()

    when (this) {
        DemoFixture.DELIVERED -> store.receive(ServerMessage.Spoken(secondTurn))
        DemoFixture.NOT_DELIVERED -> store.receive(ServerMessage.NotDelivered(secondTurn, "no_confirmation"))
        DemoFixture.DELIVERED_DESPITE_STOP -> {
            model.stop()
            store.receive(ServerMessage.Error(ActiveCallViewModel.CANNOT_INTERRUPT, "Bolna is already speaking."))
            store.receive(ServerMessage.Spoken(secondTurn))
        }
        DemoFixture.STOPPED -> {
            model.stop()
            store.receive(ServerMessage.NotDelivered(secondTurn, "stopped"))
        }
        DemoFixture.STOP_TOO_LATE -> {
            model.stop()
            store.receive(ServerMessage.Error(ActiveCallViewModel.CANNOT_INTERRUPT, "Bolna is already speaking."))
        }
        DemoFixture.BACKEND_ERROR -> {
            store.receive(ServerMessage.NotDelivered(secondTurn, "no_confirmation"))
            store.add(Chip.recognised(Sign.YES))
            store.receive(ServerMessage.Error("stale_turn", "That turn is closed; start a new one."))
        }
        DemoFixture.ENDED, DemoFixture.HANG_UP_UNCONFIRMED -> {
            store.receive(ServerMessage.Caption("Yes, 10:30 tomorrow morning.", now()))
            store.receive(ServerMessage.Caption(DemoScript.GOODBYE, now(), CaptionSpeaker.AGENT))
            model.end()
            if (this == DemoFixture.HANG_UP_UNCONFIRMED) {
                store.receive(ServerMessage.Error(ActiveCallViewModel.END_FAILED, "Could not reach Bolna to hang up."))
            }
        }
        DemoFixture.CONNECTION_LOST -> store.connectionLost()
        else -> Unit
    }
    return model
}
