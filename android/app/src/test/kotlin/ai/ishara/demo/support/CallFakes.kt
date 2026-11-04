package ai.ishara.demo.support

import ai.ishara.demo.call.CallDriver
import ai.ishara.demo.call.CallDriverError
import ai.ishara.demo.call.ReconnectStop
import ai.ishara.demo.core.call.Brief
import ai.ishara.demo.core.call.BriefRequest
import ai.ishara.demo.core.call.CallCommand
import ai.ishara.demo.core.call.CallNotes
import ai.ishara.demo.core.call.CallSnapshot
import ai.ishara.demo.core.call.CallState
import ai.ishara.demo.core.call.CallStore
import ai.ishara.demo.core.call.SendingPhase
import ai.ishara.demo.core.call.StopProgress
import ai.ishara.demo.models.CallSetup
import ai.ishara.demo.recognition.GetReadyModel
import ai.ishara.demo.recognition.LiveCamera
import ai.ishara.demo.recognition.RecognitionController
import ai.ishara.demo.recognition.RecognitionEvent
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.receiveAsFlow

/** A `TurnStore` snapshot with quiet defaults; tests set what they look at. */
fun snapshot(state: CallState = CallState.IN_CALL) = CallSnapshot(
    state = state,
    captions = emptyList(),
    currentTurnId = "turn1",
    chips = emptyList(),
    sending = SendingPhase.Idle,
    stopProgress = StopProgress.NONE,
    isComposing = false,
    followUps = emptyList(),
    steppedIn = 0,
    canSend = false,
    canResend = false,
    isStopRequested = false,
    recognisedSigns = emptyList(),
)

/**
 * Stands in for the Swift store on the JVM: records each command and shows whatever snapshot
 * the test sets. The real SEND rules are tested against Swift on the device.
 */
class FakeStore(initial: CallSnapshot = snapshot()) : CallStore {
    val state = MutableStateFlow(initial)
    override val snapshot: StateFlow<CallSnapshot> = state
    val commands = mutableListOf<CallCommand>()

    /** The kinds of the chips added, in order. */
    val added get() = commands.filterIsInstance<CallCommand.Add>().map { it.chip.kind }

    /** What `answerIfAsked` answers: true when the sign answered an open question. */
    var answersSigns = false

    override fun run(command: CallCommand): Boolean? {
        commands += command
        return when (command) {
            is CallCommand.AnswerIfAsked -> answersSigns
            is CallCommand.Add, is CallCommand.Say, is CallCommand.Answer -> true
            else -> null
        }
    }

    fun update(change: (CallSnapshot) -> CallSnapshot) {
        state.value = change(state.value)
    }
}

/** Hands the model a [FakeStore], or fails like the backend; plays canned notes. */
class StubDriver(val store: FakeStore = FakeStore()) : CallDriver {
    var startError: Exception? = null
    val startedWith = mutableListOf<CallSetup>()
    var closeCount = 0
    var briefResult: Result<Brief> = Result.success(
        Brief(briefId = "b1", text = "Call on behalf of Riya.", goal = "book a doctor's appointment", constraints = emptyList()),
    )
    val briefRequests = mutableListOf<BriefRequest>()

    /** Played in order, repeating the last one. */
    var notesResults: MutableList<Result<CallNotes>> = mutableListOf()
    var notesCalls = 0

    override var onReconnectStopped: ((ReconnectStop) -> Unit)? = null

    override suspend fun start(setup: CallSetup): CallStore {
        startedWith += setup
        startError?.let { throw it }
        return store
    }

    override fun close() {
        closeCount += 1
    }

    override suspend fun createBrief(request: BriefRequest): Brief {
        briefRequests += request
        return briefResult.getOrThrow()
    }

    override suspend fun notes(): CallNotes {
        notesCalls += 1
        val next = notesResults.firstOrNull() ?: throw CallDriverError.NoCall
        if (notesResults.size > 1) notesResults.removeAt(0)
        return next.getOrThrow()
    }
}

/** A recognizer the test drives by hand. */
class StubRecognition : RecognitionController {
    override val getReady = GetReadyModel()
    override val failure = MutableStateFlow<String?>(null)
    override val notice = MutableStateFlow<String?>(null)
    override val camera: LiveCamera? = null
    override val replayOptions: List<String> = emptyList()
    var startCount = 0
    var stopCount = 0
    private var events: Channel<RecognitionEvent>? = null

    override fun start() {
        startCount += 1
    }

    override fun signingEvents(): Flow<RecognitionEvent> {
        val channel = Channel<RecognitionEvent>(Channel.UNLIMITED)
        events = channel
        return channel.receiveAsFlow()
    }

    override fun replay(option: String) = Unit

    override fun stop() {
        stopCount += 1
        events?.close()
    }

    fun emit(event: RecognitionEvent) {
        events?.trySend(event)
    }
}
