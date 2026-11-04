package ai.ishara.demo.core.call

import kotlinx.coroutines.flow.Flow
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** Where the backend lives and the demo app token. */
data class BackendConfig(val baseUrl: String, val appToken: String) {
    override fun toString() = "BackendConfig(baseUrl=$baseUrl, appToken=<redacted>)"
}

/** The backend calls a call driver needs; [CallCore] runs them through CallSession's `BackendClient`. */
interface CallBackend {
    /** `POST /calls`, then opens the call socket. */
    suspend fun startCall(request: StartCallRequest): LiveCallSession

    /** `POST /briefs`. */
    suspend fun createBrief(request: BriefRequest): Brief

    /** `GET /calls/{id}/notes`. */
    suspend fun notes(callId: String): CallNotes
}

/** One placed call: CallSession's `LiveCall`. */
interface LiveCallSession {
    val callId: String
    val store: CallStore

    /** Emits when the call socket closed on its own; the store has already gone silent. */
    val connectionLost: Flow<Unit>

    /** Why the socket last closed; null while it is open. */
    suspend fun lastClose(): SocketClose?

    /** Reopens the socket. Does nothing after a close a reconnect can't fix. */
    suspend fun connect()

    /** Disconnects and frees the call. Sends nothing. */
    fun close()
}

/** CallSession's `CallSocketClose`, from the backend's close codes. */
@Serializable
enum class CallSocketClose {
    @SerialName("dropped") DROPPED,
    @SerialName("unauthorized") UNAUTHORIZED,
    @SerialName("unknownCall") UNKNOWN_CALL,
    @SerialName("replaced") REPLACED,
}

/** [allowsReconnect] comes from CallSession: only a plain drop may be reconnected. */
@Serializable
data class SocketClose(val kind: CallSocketClose, val allowsReconnect: Boolean)

/** A failed backend call, as the Swift bridge reports it. */
class CallCoreException(val kind: Kind, val status: Int?, message: String) : Exception(message) {
    @Serializable
    enum class Kind {
        /** 401: the app token was refused. */
        @SerialName("unauthorized") UNAUTHORIZED,

        /** 403: the number isn't on the backend's allowlist. */
        @SerialName("forbidden") FORBIDDEN,

        @SerialName("notFound") NOT_FOUND,

        /** 422: the backend rejected the body (often an older backend). */
        @SerialName("validation") VALIDATION,

        @SerialName("server") SERVER,

        /** Any other non-2xx status. */
        @SerialName("http") HTTP,
        @SerialName("notHTTPResponse") NOT_HTTP_RESPONSE,

        /** The backend's answer didn't decode. */
        @SerialName("decoding") DECODING,

        /** No connection: host unreachable, timeout and so on. */
        @SerialName("transport") TRANSPORT,
        @SerialName("notConfigured") NOT_CONFIGURED,
        @SerialName("unknownSession") UNKNOWN_SESSION,
        @SerialName("unexpected") UNEXPECTED,
    }
}
