package ai.ishara.demo.core.call

import ai.ishara.demo.core.CoreEvents
import ai.ishara.demo.core.IsharaCore
import android.os.Handler
import android.os.Looper
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.long
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicLong
import kotlin.coroutines.resumeWithException

/**
 * CallSession, running in the Swift core: live calls through its `BackendClient` and
 * `LiveCall`, and local sessions whose `TurnStore` Kotlin feeds (the fake call, tests).
 * Session actions run on the main thread; suspend functions may be called from anywhere.
 */
object CallCore : CallBackend {
    private val nextRequestId = AtomicLong()
    private val pending = ConcurrentHashMap<Long, (JsonObject) -> Unit>()
    private val sessions = ConcurrentHashMap<Int, CallSessionHandle>()

    init {
        IsharaCore.setSocketBridge(OkHttpWebSockets)
        CoreEvents.subscribe("result") { event -> pending.remove(event.getValue("requestId").jsonPrimitive.long)?.invoke(event) }
        CoreEvents.subscribe("state") { event ->
            session(event)?.update(CoreJson.decodeFromJsonElement(CallSnapshot.serializer(), event.getValue("snapshot")))
        }
        CoreEvents.subscribe("outgoing") { event ->
            val message = CoreJson.decodeFromJsonElement(AppMessage.serializer(), event.getValue("message"))
            (session(event) as? LocalCallSession)?.deliver(Outgoing.Message(message))
        }
        CoreEvents.subscribe("discardPending") { event -> (session(event) as? LocalCallSession)?.deliver(Outgoing.DiscardPending) }
        CoreEvents.subscribe("connectionLost") { event -> (session(event) as? LiveCallHandle)?.lost() }
    }

    fun configureBackend(config: BackendConfig) {
        IsharaCore.configureBackend(config.baseUrl, config.appToken)
    }

    /** A store whose outgoing messages come out of [LocalCallSession.outgoing]. Main thread only. */
    fun startLocalSession(initialState: CallState = CallState.DIALING): LocalCallSession {
        val request = CoreJson.encodeToString(LocalStart.serializer(), LocalStart(initialState))
        val start = CoreJson.decodeFromString(SessionStart.serializer(), IsharaCore.startLocalSession(request))
        return LocalCallSession(start.sessionId, start.snapshot).also { sessions[it.id] = it }
    }

    override suspend fun startCall(request: StartCallRequest): LiveCallHandle = request(
        start = { id -> IsharaCore.startLiveCall(id, CoreJson.encodeToString(StartCallRequest.serializer(), request)) },
        onValue = { value ->
            // Registered here, on the event thread, so no event of the new session is missed.
            val start = CoreJson.decodeFromJsonElement(SessionStart.serializer(), value)
            LiveCallHandle(start.sessionId, checkNotNull(start.callId), start.snapshot).also { sessions[it.id] = it }
        },
        // The caller was cancelled after Swift placed the call: let it go (on the main thread).
        discard = { call -> Handler(Looper.getMainLooper()).post(call::close) },
    )

    override suspend fun createBrief(request: BriefRequest): Brief = request(
        start = { id -> IsharaCore.createBrief(id, CoreJson.encodeToString(BriefRequest.serializer(), request)) },
        onValue = { CoreJson.decodeFromJsonElement(Brief.serializer(), it) },
    )

    override suspend fun notes(callId: String): CallNotes = request(
        start = { id -> IsharaCore.fetchNotes(id, callId) },
        onValue = { CoreJson.decodeFromJsonElement(CallNotes.serializer(), it) },
    )

    internal suspend fun connect(sessionId: Int) {
        request(start = { id -> IsharaCore.connect(id, sessionId) }, onValue = {})
    }

    internal suspend fun lastClose(sessionId: Int): SocketClose? = request(
        start = { id -> IsharaCore.lastClose(id, sessionId) },
        onValue = { value -> if (value is JsonNull) null else CoreJson.decodeFromJsonElement(SocketClose.serializer(), value) },
    )

    internal fun command(sessionId: Int, command: CallCommand): Boolean? {
        val result = IsharaCore.command(sessionId, CoreJson.encodeToString(CallCommand.serializer(), command))
        return CoreJson.parseToJsonElement(result).jsonObject["value"]?.jsonPrimitive?.booleanOrNull
    }

    internal fun receive(sessionId: Int, message: ServerMessage) {
        IsharaCore.receive(sessionId, CoreJson.encodeToString(ServerMessage.serializer(), message))
    }

    internal fun close(sessionId: Int) {
        sessions.remove(sessionId)
        IsharaCore.closeSession(sessionId)
    }

    private fun session(event: JsonObject) = sessions[event.getValue("sessionId").jsonPrimitive.int]

    /** Starts an async Swift call with a fresh request id and waits for its `result` event. */
    private suspend fun <T> request(start: (Long) -> Unit, onValue: (JsonElement) -> T, discard: (T) -> Unit = {}): T {
        val id = nextRequestId.incrementAndGet()
        return suspendCancellableCoroutine { continuation ->
            pending[id] = { event ->
                if (event.getValue("ok").jsonPrimitive.boolean) {
                    runCatching { onValue(event["value"] ?: JsonNull) }.fold(
                        onSuccess = { value -> continuation.resume(value) { _, unused, _ -> discard(unused) } },
                        onFailure = continuation::resumeWithException,
                    )
                } else {
                    val error = CoreJson.decodeFromJsonElement(ResultError.serializer(), event.getValue("error"))
                    continuation.resumeWithException(CallCoreException(error.kind, error.status, error.message))
                }
            }
            try {
                start(id)
            } catch (e: Throwable) {
                pending.remove(id)
                throw e
            }
        }
    }

    @Serializable
    private data class LocalStart(val initialState: CallState)

    @Serializable
    private data class SessionStart(val sessionId: Int, val callId: String? = null, val snapshot: CallSnapshot)

    @Serializable
    private data class ResultError(val kind: CallCoreException.Kind, val status: Int? = null, val message: String)
}

/** One `TurnStore` in the Swift core. Its actions must run on the main thread. */
open class CallSessionHandle internal constructor(val id: Int, initial: CallSnapshot) : CallStore, AutoCloseable {
    private val state = MutableStateFlow(initial)
    override val snapshot: StateFlow<CallSnapshot> = state.asStateFlow()

    @Volatile
    private var closed = false

    internal fun update(snapshot: CallSnapshot) {
        state.value = snapshot
    }

    override fun run(command: CallCommand): Boolean? {
        check(!closed) { "call session $id is closed" }
        return CallCore.command(id, command)
    }

    /** Stops snapshots and frees the store (a live call is disconnected first). Sends nothing. Main thread only. */
    override fun close() {
        if (closed) return
        closed = true
        CallCore.close(id)
        onClose()
    }

    protected open fun onClose() {}
}

/** What a local session's store sends: a wire message, or "drop what you haven't sent yet". */
sealed interface Outgoing {
    data class Message(val message: AppMessage) : Outgoing

    data object DiscardPending : Outgoing
}

/**
 * A store with no socket: Kotlin plays the backend, feeding [receive] and reading [outgoing].
 * [outgoing] is buffered from the start, so nothing is missed before it is collected; collect it once.
 */
class LocalCallSession internal constructor(id: Int, initial: CallSnapshot) : CallSessionHandle(id, initial) {
    private val outgoingChannel = Channel<Outgoing>(Channel.UNLIMITED)
    val outgoing: Flow<Outgoing> = outgoingChannel.receiveAsFlow()

    /**
     * Takes what the store sends instead of [outgoing], inside the action that sent it, like
     * CallSession's `OutgoingMessageSink`: [receive] may be called from it, before the action
     * finishes (the fake call's goodbye lands before `end()` closes the store). Set it before
     * the first action. Main thread only.
     */
    var sink: ((Outgoing) -> Unit)? = null

    /** Applies a backend message to the store, exactly as a socket frame would be. Main thread only. */
    fun receive(message: ServerMessage) {
        CallCore.receive(id, message)
    }

    internal fun deliver(item: Outgoing) {
        val sink = sink
        if (sink != null) sink(item) else outgoingChannel.trySend(item)
    }

    override fun onClose() {
        outgoingChannel.close()
    }
}

/** A placed call (CallSession's `LiveCall`). [connectionLost] is buffered; collect it once. */
class LiveCallHandle internal constructor(id: Int, override val callId: String, initial: CallSnapshot) :
    CallSessionHandle(id, initial), LiveCallSession {
    private val lostChannel = Channel<Unit>(Channel.UNLIMITED)
    override val connectionLost: Flow<Unit> = lostChannel.receiveAsFlow()
    override val store: CallStore get() = this

    override suspend fun lastClose(): SocketClose? = CallCore.lastClose(id)

    override suspend fun connect() = CallCore.connect(id)

    internal fun lost() {
        lostChannel.trySend(Unit)
    }

    override fun onClose() {
        lostChannel.close()
    }
}
