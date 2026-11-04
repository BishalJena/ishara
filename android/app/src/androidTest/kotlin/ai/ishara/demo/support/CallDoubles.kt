package ai.ishara.demo.support

import ai.ishara.demo.call.CallDriver
import ai.ishara.demo.call.CallDriverError
import ai.ishara.demo.call.ReconnectStop
import ai.ishara.demo.core.call.AppMessage
import ai.ishara.demo.core.call.Brief
import ai.ishara.demo.core.call.BriefRequest
import ai.ishara.demo.core.call.CallCore
import ai.ishara.demo.core.call.CallNotes
import ai.ishara.demo.core.call.CallState
import ai.ishara.demo.core.call.CallStore
import ai.ishara.demo.core.call.LocalCallSession
import ai.ishara.demo.core.call.Outgoing
import ai.ishara.demo.core.call.onMain
import ai.ishara.demo.models.CallSetup
import ai.ishara.demo.recognition.GetReadyModel
import ai.ishara.demo.recognition.LiveCamera
import ai.ishara.demo.recognition.RecognitionController
import ai.ishara.demo.recognition.RecognitionEvent
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.launch
import java.util.concurrent.CopyOnWriteArrayList

const val WAIT_MS = 5_000L

/** Polls [condition] on the main thread until it holds or [timeoutMs] passes. */
fun eventually(timeoutMs: Long = WAIT_MS, condition: () -> Boolean): Boolean {
    val deadline = System.currentTimeMillis() + timeoutMs
    while (System.currentTimeMillis() < deadline) {
        if (onMain(condition)) return true
        Thread.sleep(10)
    }
    return onMain(condition)
}

/** Runs [block] on the main thread until the test cancels the returned job. */
fun launchOnMain(block: suspend CoroutineScope.() -> Unit): Job =
    CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate).launch(block = block)

/**
 * Hands the view model a real Swift `TurnStore` whose messages are recorded instead of sent,
 * like iOS's `StubCallDriver` with its `RecordingSink`. Create it on the main thread.
 */
class RecordingDriver(initialState: CallState = CallState.DIALING) : CallDriver {
    val sent = CopyOnWriteArrayList<AppMessage>()
    val store: LocalCallSession = CallCore.startLocalSession(initialState).also { session ->
        session.sink = { item -> if (item is Outgoing.Message) sent += item.message }
    }
    val startedWith = mutableListOf<CallSetup>()
    var startError: Exception? = null
    var closeCount = 0

    override var onReconnectStopped: ((ReconnectStop) -> Unit)? = null

    val approvals: List<AppMessage.Approve> get() = sent.filterIsInstance<AppMessage.Approve>()
    val chipUpdates: List<AppMessage.Chips> get() = sent.filterIsInstance<AppMessage.Chips>()

    override suspend fun start(setup: CallSetup): CallStore {
        startedWith += setup
        startError?.let { throw it }
        return store
    }

    override fun close() {
        closeCount += 1
    }

    override suspend fun createBrief(request: BriefRequest): Brief = Brief("b1", "Call on behalf of Riya.", "book a doctor's appointment", emptyList())

    override suspend fun notes(): CallNotes = throw CallDriverError.NoCall
}

/** A recognizer the test drives by hand. */
class StubRecognition : RecognitionController {
    override val getReady = GetReadyModel()
    override val failure = MutableStateFlow<String?>(null)
    override val notice = MutableStateFlow<String?>(null)
    override val camera: LiveCamera? = null
    override val replayOptions: List<String> = emptyList()
    var stopCount = 0
    private var events: Channel<RecognitionEvent>? = null

    override fun start() = Unit

    override fun signingEvents(): Flow<RecognitionEvent> = Channel<RecognitionEvent>(Channel.UNLIMITED).also { events = it }.receiveAsFlow()

    override fun replay(option: String) = Unit

    override fun stop() {
        stopCount += 1
        events?.close()
    }

    fun emit(event: RecognitionEvent) {
        events?.trySend(event)
    }
}
