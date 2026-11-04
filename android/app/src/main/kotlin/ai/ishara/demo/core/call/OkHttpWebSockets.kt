package ai.ishara.demo.core.call

import ai.ishara.demo.core.IsharaCore
import kotlinx.serialization.builtins.MapSerializer
import kotlinx.serialization.builtins.serializer
import okhttp3.Headers.Companion.toHeaders
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/**
 * The call sockets, run for Swift's `KotlinWebSocketTransport` (Call/KotlinWebSocketTransport.swift),
 * which calls these methods over JNI. Frames and closes go back through [IsharaCore.socketMessage]
 * and [IsharaCore.socketClosed], with the server's close code as sent.
 */
internal object OkHttpWebSockets {
    /** No close frame arrived (network loss, refused upgrade, failed ping). */
    private const val NO_CLOSE_FRAME = -1
    private const val NORMAL_CLOSURE = 1000

    // Heroku closes a socket idle for 55 s; matches URLSessionWebSocketTransport.defaultPingInterval.
    private val client = OkHttpClient.Builder().pingInterval(20, TimeUnit.SECONDS).build()
    private val sockets = ConcurrentHashMap<Long, WebSocket>()
    private val headersSerializer = MapSerializer(String.serializer(), String.serializer())

    fun connect(id: Long, url: String, headersJson: String) {
        val request = Request.Builder()
            .url(url)
            .headers(CoreJson.decodeFromString(headersSerializer, headersJson).toHeaders())
            .build()
        val listener = Listener(id)
        sockets[id] = client.newWebSocket(request, listener)
        if (listener.isFinished) sockets.remove(id)
    }

    /** False when the socket is gone or closing. */
    fun send(id: Long, text: String): Boolean = sockets[id]?.send(text) ?: false

    fun close(id: Long) {
        sockets.remove(id)?.close(NORMAL_CLOSURE, null)
    }

    private class Listener(private val id: Long) : WebSocketListener() {
        private val finished = AtomicBoolean(false)
        val isFinished: Boolean get() = finished.get()

        override fun onMessage(webSocket: WebSocket, text: String) {
            IsharaCore.socketMessage(id, text)
        }

        override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
            IsharaCore.socketMessage(id, bytes.utf8())
        }

        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
            webSocket.close(NORMAL_CLOSURE, null)
            finish(code)
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            finish(code)
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            finish(NO_CLOSE_FRAME)
        }

        /** Reports the first close only; Swift ignores reports for sockets it already let go of. */
        private fun finish(code: Int) {
            if (!finished.compareAndSet(false, true)) return
            sockets.remove(id)
            IsharaCore.socketClosed(id, code)
        }
    }
}
