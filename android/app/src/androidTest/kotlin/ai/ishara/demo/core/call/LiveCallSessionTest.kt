package ai.ishara.demo.core.call

import ai.ishara.demo.call.LiveCallDriver
import ai.ishara.demo.call.ReconnectStop
import ai.ishara.demo.models.CallSetup
import androidx.test.ext.junit.runners.AndroidJUnit4
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.MainScope
import kotlinx.coroutines.cancel
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import mockwebserver3.Dispatcher
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import mockwebserver3.RecordedRequest
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.net.InetAddress
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import kotlin.time.Duration

/**
 * A live call through CallSession's `BackendClient` and `LiveCall` in the Swift core,
 * against an in-process fake backend (HTTP plus the call WebSocket).
 */
@RunWith(AndroidJUnit4::class)
class LiveCallSessionTest {
    private val backend = FakeBackend()
    private val server = MockWebServer()
    private val calls = mutableListOf<LiveCallHandle>()

    @Before
    fun setUp() {
        server.dispatcher = backend
        server.start(InetAddress.getByName("127.0.0.1"), 0)
        CallCore.configureBackend(BackendConfig(baseUrl = "http://127.0.0.1:${server.port}", appToken = TOKEN))
    }

    @After
    fun tearDown() {
        onMain { calls.forEach(LiveCallHandle::close) }
        server.close()
    }

    private fun startCall(): LiveCallHandle = runBlocking {
        CallCore.startCall(StartCallRequest(contactId = "clinic", purpose = CallPurpose.DOCTOR_APPOINTMENT))
    }.also { calls += it }

    @Test
    fun aLiveCallRunsOverTheBackendsRestAndSocket() {
        val call = startCall()

        assertEquals("call_1", call.callId)
        val start = backend.requests.take("/calls")
        assertEquals("POST", start.method)
        assertEquals("Bearer $TOKEN", start.headers["Authorization"])
        assertEquals(
            """{"attended":false,"contact_id":"clinic","mode":"live","purpose":"doctor_appointment"}""",
            start.body?.utf8(),
        )
        val socket = backend.awaitSocket()
        val upgrade = backend.requests.take("/calls/call_1/ws")
        assertEquals("Bearer $TOKEN", upgrade.headers["Authorization"])

        socket.send("""{"type":"status","state":"in_call"}""")
        socket.send("""{"type":"caption","text":"City Clinic, how can I help?","at":1793430000.25}""")
        val live = call.awaitSnapshot { it.state == CallState.IN_CALL && it.captions.isNotEmpty() }
        assertEquals(Caption("City Clinic, how can I help?", 1_793_430_000.25, Caption.Speaker.RECEPTIONIST), live.captions.single())

        onMain { call.add(Chip.recognised(Sign.HELLO)) }
        val turn = call.snapshot.value.currentTurnId
        assertEquals("""{"chips":["hello"],"turn_id":"$turn","type":"chips"}""", backend.awaitFrame())
        socket.send("""{"type":"draft","turn_id":"$turn","text":"Hello, 10/30 please.","source":"llm"}""")
        call.awaitSnapshot { it.canSend }
        backend.assertNoFrame()

        onMain { call.send() }

        assertEquals("""{"text":"Hello, 10/30 please.","turn_id":"$turn","type":"approve"}""", backend.awaitFrame())
    }

    @Test
    fun aReplacedSocketIsLostSilentAndNotReconnectable() {
        val call = startCall()
        val socket = backend.awaitSocket()
        socket.send("""{"type":"status","state":"in_call"}""")
        call.awaitSnapshot { it.state == CallState.IN_CALL }
        assertNull("an open socket has no close", runBlocking { call.lastClose() })

        socket.close(4409, "replaced")

        call.connectionLost.awaitFirst()
        val silent = call.snapshot.value
        assertEquals(CallState.ERROR, silent.state)
        assertEquals("Nothing will be sent", silent.notice)
        assertEquals(SocketClose(CallSocketClose.REPLACED, allowsReconnect = false), runBlocking { call.lastClose() })
    }

    @Test
    fun aRefusedTokenOnTheSocketIsUnauthorized() {
        val call = startCall()

        backend.awaitSocket().close(4401, "unauthorized")

        call.connectionLost.awaitFirst()
        assertEquals(SocketClose(CallSocketClose.UNAUTHORIZED, allowsReconnect = false), runBlocking { call.lastClose() })
    }

    @Test
    fun theDriverReconnectsADroppedSocketAndResendsNothing() = withDriver { driver, stops ->
        val store = runBlocking { onMainSuspend { driver.start(CallSetup.demo) } }
        val first = backend.awaitSocket()
        first.send("""{"type":"status","state":"in_call"}""")
        store.awaitSnapshot { it.state == CallState.IN_CALL }
        onMain { store.useQuickReply(QuickReply.YES) }
        store.awaitSnapshot { it.draft != null }

        first.close(1001, "going away")

        val second = backend.awaitSocket()
        val reconnect = backend.requests.last()
        assertEquals("/calls/call_1/ws", reconnect.url.encodedPath)
        assertEquals("Bearer $TOKEN", reconnect.headers["Authorization"])
        assertNull("the draft was wiped", store.awaitSnapshot { it.state == CallState.ERROR }.draft)
        second.send("""{"type":"status","state":"in_call"}""")
        store.awaitSnapshot { it.state == CallState.IN_CALL }
        backend.assertNoFrame()
        assertNull("the driver gave up on a plain drop", stops.poll())
    }

    @Test
    fun theDriverNeverReconnectsAReplacedSocket() = withDriver { driver, stops ->
        runBlocking { onMainSuspend { driver.start(CallSetup.demo) } }

        backend.awaitSocket().close(4409, "replaced")

        assertEquals(ReconnectStop.Refused(CallSocketClose.REPLACED), stops.poll(TIMEOUT_MS, TimeUnit.MILLISECONDS))
        assertNull("a replaced socket was reopened", backend.sockets.poll(500, TimeUnit.MILLISECONDS))
    }

    private fun withDriver(body: (LiveCallDriver, LinkedBlockingQueue<ReconnectStop>) -> Unit) {
        val scope = MainScope()
        val stops = LinkedBlockingQueue<ReconnectStop>()
        val driver = LiveCallDriver(CallCore, reconnectDelays = listOf(Duration.ZERO), scope = scope)
        driver.onReconnectStopped = { stops.add(it) }
        try {
            body(driver, stops)
        } finally {
            onMain { driver.close() }
            scope.cancel()
        }
    }

    @Test
    fun briefsAndNotesComeBackDecoded() {
        val brief = runBlocking {
            CallCore.createBrief(BriefRequest(CallPurpose.DOCTOR_APPOINTMENT, listOf(Sign.TOMORROW), Profile(name = "Riya")))
        }
        val notes = runBlocking { CallCore.notes("call_9") }

        assertEquals(Brief("b7", "Call on behalf of Riya.", "book a doctor's appointment", emptyList()), brief)
        assertEquals(
            """{"chips":["tomorrow"],"profile":{"details":[],"name":"Riya"},"purpose":"doctor_appointment"}""",
            backend.requests.take("/briefs").body?.utf8(),
        )
        assertEquals("GET", backend.requests.take("/calls/call_9/notes").method)
        assertEquals("booked", notes.outcome)
        assertEquals(listOf(TranscriptEntry(CaptionSpeaker.RECEPTIONIST, "Booked.", 1.0)), notes.transcript)
    }

    @Test
    fun aRefusedTokenIsUnauthorized() {
        CallCore.configureBackend(BackendConfig(baseUrl = "http://127.0.0.1:${server.port}", appToken = "wrong"))

        val error = runCatching { startCall() }.exceptionOrNull() as CallCoreException

        assertEquals(CallCoreException.Kind.UNAUTHORIZED, error.kind)
        assertEquals(401, error.status)
        assertNull("no socket after a refused start", backend.sockets.poll(300, TimeUnit.MILLISECONDS))
    }

    @Test
    fun anUnreachableBackendIsATransportError() {
        val port = server.port
        server.close()
        CallCore.configureBackend(BackendConfig(baseUrl = "http://127.0.0.1:$port", appToken = TOKEN))

        val error = runCatching { startCall() }.exceptionOrNull() as CallCoreException

        assertEquals(CallCoreException.Kind.TRANSPORT, error.kind)
    }

    private suspend fun <T> onMainSuspend(block: suspend () -> T): T = withContext(Dispatchers.Main) { block() }

    private fun LinkedBlockingQueue<RecordedRequest>.take(path: String): RecordedRequest {
        val request = poll(TIMEOUT_MS, TimeUnit.MILLISECONDS) ?: throw AssertionError("no request for $path")
        assertEquals(path, request.url.encodedPath)
        return request
    }

    /** The backend's routes, each checking the app token like backend/app/auth.py. */
    private class FakeBackend : Dispatcher() {
        val requests = LinkedBlockingQueue<RecordedRequest>()
        val sockets = LinkedBlockingQueue<WebSocket>()
        private val frames = LinkedBlockingQueue<String>()
        private var callCount = 0

        override fun dispatch(request: RecordedRequest): MockResponse {
            requests.add(request)
            if (request.headers["Authorization"] != "Bearer $TOKEN") return json(401, """{"detail":"bad token"}""")
            val path = request.url.encodedPath
            return when {
                path == "/calls" && request.method == "POST" -> {
                    callCount += 1
                    json(200, """{"call_id":"call_$callCount","state":"dialing","mode":"live"}""")
                }
                path.matches(Regex("/calls/call_\\d+/ws")) -> MockResponse.Builder().webSocketUpgrade(socketListener).build()
                path == "/briefs" && request.method == "POST" ->
                    json(200, """{"brief_id":"b7","text":"Call on behalf of Riya.","goal":"book a doctor's appointment","constraints":[]}""")
                path == "/calls/call_9/notes" -> json(
                    200,
                    """{"call_id":"call_9","mode":"delegated","ready":true,"outcome":"booked","summary":[],"open_questions":[],"transcript":[{"speaker":"receptionist","text":"Booked.","at":1}],"bolna_summary":null}""",
                )
                else -> json(404, """{"detail":"not found"}""")
            }
        }

        private val socketListener = object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                sockets.add(webSocket)
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                frames.add(text)
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                webSocket.close(code, null)
            }
        }

        fun awaitSocket(): WebSocket = sockets.poll(TIMEOUT_MS, TimeUnit.MILLISECONDS) ?: throw AssertionError("no socket opened")

        fun awaitFrame(): String = frames.poll(TIMEOUT_MS, TimeUnit.MILLISECONDS) ?: throw AssertionError("no frame received")

        fun assertNoFrame() {
            val frame = frames.poll(300, TimeUnit.MILLISECONDS)
            assertTrue("unexpected frame $frame", frame == null)
        }

        private fun json(code: Int, body: String) =
            MockResponse.Builder().code(code).addHeader("Content-Type", "application/json").body(body).build()
    }

    private companion object {
        const val TOKEN = "test-token"
    }
}
