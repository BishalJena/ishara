package ai.ishara.demo.call

import ai.ishara.demo.core.call.Brief
import ai.ishara.demo.core.call.BriefRequest
import ai.ishara.demo.core.call.CallBackend
import ai.ishara.demo.core.call.CallCommand
import ai.ishara.demo.core.call.CallCoreException
import ai.ishara.demo.core.call.CallMode
import ai.ishara.demo.core.call.CallNotes
import ai.ishara.demo.core.call.CallPurpose
import ai.ishara.demo.core.call.CallSnapshot
import ai.ishara.demo.core.call.CallSocketClose
import ai.ishara.demo.core.call.CallState
import ai.ishara.demo.core.call.CallStore
import ai.ishara.demo.core.call.CoreJson
import ai.ishara.demo.core.call.LiveCallSession
import ai.ishara.demo.core.call.Profile
import ai.ishara.demo.core.call.SendingPhase
import ai.ishara.demo.core.call.Sign
import ai.ishara.demo.core.call.SocketClose
import ai.ishara.demo.core.call.StartCallRequest
import ai.ishara.demo.core.call.StopProgress
import ai.ishara.demo.models.CallSetup
import ai.ishara.demo.models.Delegation
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.time.Duration
import kotlin.time.Duration.Companion.seconds

/** Mirrors ios/IsharaTests/LiveCallDriverTests.swift against an in-memory backend. */
class LiveCallDriverTest {
    private val backend = FakeBackend()
    private val sleeps = mutableListOf<Duration>()
    private val stops = mutableListOf<ReconnectStop>()

    private fun TestScope.makeDriver(
        reconnectDelays: List<Duration> = listOf(Duration.ZERO, Duration.ZERO),
        sleep: suspend (Duration) -> Unit = { sleeps += it },
    ) = LiveCallDriver(backend, reconnectDelays, sleep, backgroundScope).also { driver ->
        driver.onReconnectStopped = { stops += it }
    }

    @Test
    fun startAsksTheBackendForTheChosenContactAndReturnsItsStore() = runTest {
        val driver = makeDriver()

        val store = driver.start(CallSetup.demo)

        assertEquals(listOf(StartCallRequest(contactId = "clinic", purpose = CallPurpose.DOCTOR_APPOINTMENT)), backend.starts)
        assertEquals(
            Json.parseToJsonElement("""{"attended":false,"contact_id":"clinic","mode":"live","purpose":"doctor_appointment"}"""),
            CoreJson.encodeToJsonElement(StartCallRequest.serializer(), backend.starts.single()),
        )
        assertSame(backend.sessions.single().store, store)
    }

    @Test
    fun refusedStartThrowsAndLeavesNoCall() = runTest {
        backend.startFailure = CallCoreException(CallCoreException.Kind.UNAUTHORIZED, 401, "refused")
        val driver = makeDriver()

        val error = runCatching { driver.start(CallSetup.demo) }.exceptionOrNull()

        assertEquals(CallCoreException.Kind.UNAUTHORIZED, (error as CallCoreException).kind)
        assertSame(CallDriverError.NoCall, runCatching { driver.notes() }.exceptionOrNull())
    }

    @Test
    fun droppedSocketReconnectsOnce() = runTest {
        val driver = makeDriver()
        driver.start(CallSetup.demo)
        val call = backend.sessions.single()

        call.drop(SocketClose(CallSocketClose.DROPPED, allowsReconnect = true))
        runCurrent()

        assertEquals(1, call.connects)
        assertEquals(emptyList<ReconnectStop>(), stops)
    }

    @Test
    fun socketThatDiedWithoutACloseFrameReconnects() = runTest {
        val driver = makeDriver()
        driver.start(CallSetup.demo)
        val call = backend.sessions.single()

        call.drop(close = null)
        runCurrent()

        assertEquals(1, call.connects)
    }

    @Test
    fun reconnectsWaitLongerEachTimeAndStopAfterTheLastScheduledAttempt() = runTest {
        val driver = makeDriver(reconnectDelays = LiveCallDriver.DEFAULT_RECONNECT_DELAYS)
        driver.start(CallSetup.demo)
        val call = backend.sessions.single()

        repeat(4) {
            call.drop(SocketClose(CallSocketClose.DROPPED, allowsReconnect = true))
            runCurrent()
        }

        assertEquals(listOf(1.seconds, 2.seconds, 4.seconds), sleeps)
        assertEquals(3, call.connects)
        assertEquals(listOf<ReconnectStop>(ReconnectStop.AttemptsUsedUp), stops)
    }

    @Test
    fun refusedSocketIsNeverReopenedAndSaysWhy() = runTest {
        for (kind in listOf(CallSocketClose.UNAUTHORIZED, CallSocketClose.UNKNOWN_CALL, CallSocketClose.REPLACED)) {
            stops.clear()
            val driver = makeDriver()
            driver.start(CallSetup.demo)
            val call = backend.sessions.last()

            call.drop(SocketClose(kind, allowsReconnect = false))
            runCurrent()

            assertEquals("$kind", 0, call.connects)
            assertEquals("$kind", listOf<ReconnectStop>(ReconnectStop.Refused(kind)), stops)
        }
    }

    @Test
    fun noReconnectOnceTheBackendReportedTheCallAgain() = runTest {
        val gate = CompletableDeferred<Unit>()
        val driver = makeDriver(sleep = { gate.await() })
        driver.start(CallSetup.demo)
        val call = backend.sessions.single()
        call.drop(SocketClose(CallSocketClose.DROPPED, allowsReconnect = true))
        runCurrent()

        call.setState(CallState.IN_CALL)
        gate.complete(Unit)
        runCurrent()

        assertEquals(0, call.connects)
    }

    @Test
    fun closeDisconnectsAndStopsReconnecting() = runTest {
        val gate = CompletableDeferred<Unit>()
        val driver = makeDriver(sleep = { gate.await() })
        driver.start(CallSetup.demo)
        val call = backend.sessions.single()
        call.drop(SocketClose(CallSocketClose.DROPPED, allowsReconnect = true))
        runCurrent()

        driver.close()
        gate.complete(Unit)
        runCurrent()

        assertTrue(call.closed)
        assertEquals(0, call.connects)
        call.drop(SocketClose(CallSocketClose.DROPPED, allowsReconnect = true))
        runCurrent()
        assertEquals(0, call.connects)
    }

    @Test
    fun delegatedFlowBuildsTheBriefStartsWithItAndFetchesTheNotes() = runTest {
        val driver = makeDriver()

        val brief = driver.createBrief(
            BriefRequest(purpose = CallPurpose.DOCTOR_APPOINTMENT, chips = listOf(Sign.TOMORROW), profile = Profile(name = "Riya")),
        )
        driver.start(CallSetup.demo.copy(delegation = Delegation(brief, attended = true)))
        driver.close()
        val notes = driver.notes()

        assertEquals(
            StartCallRequest(
                contactId = "clinic",
                purpose = CallPurpose.DOCTOR_APPOINTMENT,
                mode = CallMode.DELEGATED,
                briefId = "b7",
                attended = true,
            ),
            backend.starts.single(),
        )
        assertEquals(listOf("call_1"), backend.notesFor)
        assertEquals("booked", notes.outcome)
    }

    @Test
    fun notesBeforeAnyCallIsAnError() = runTest {
        val error = runCatching { makeDriver().notes() }.exceptionOrNull()

        assertSame(CallDriverError.NoCall, error)
        assertNull(backend.notesFor.firstOrNull())
    }

    private class FakeBackend : CallBackend {
        val starts = mutableListOf<StartCallRequest>()
        val sessions = mutableListOf<FakeCall>()
        val notesFor = mutableListOf<String>()
        var startFailure: Exception? = null

        override suspend fun startCall(request: StartCallRequest): LiveCallSession {
            startFailure?.let { throw it }
            starts += request
            return FakeCall("call_${sessions.size + 1}").also { sessions += it }
        }

        override suspend fun createBrief(request: BriefRequest) =
            Brief(briefId = "b7", text = "Call on behalf of ${request.profile.name}.", goal = "book", constraints = emptyList())

        override suspend fun notes(callId: String): CallNotes {
            notesFor += callId
            return CallNotes(callId = callId, mode = CallMode.DELEGATED, ready = true, outcome = "booked")
        }
    }

    private class FakeCall(override val callId: String) : LiveCallSession {
        private val lost = Channel<Unit>(Channel.UNLIMITED)
        private var close: SocketClose? = null
        private val fakeStore = FakeStore()
        var connects = 0
        var closed = false

        override val store: CallStore get() = fakeStore
        override val connectionLost: Flow<Unit> = lost.receiveAsFlow()

        override suspend fun lastClose() = close

        override suspend fun connect() {
            connects += 1
        }

        override fun close() {
            closed = true
        }

        /** What CallSession does on a drop: the store goes silent, then `onConnectionLost` runs. */
        fun drop(close: SocketClose?) {
            this.close = close
            setState(CallState.ERROR)
            lost.trySend(Unit)
        }

        fun setState(state: CallState) {
            fakeStore.state.value = fakeStore.state.value.copy(state = state)
        }
    }

    private class FakeStore : CallStore {
        val state = MutableStateFlow(
            CallSnapshot(
                state = CallState.DIALING, captions = emptyList(), currentTurnId = "turn1", chips = emptyList(),
                sending = SendingPhase.Idle, stopProgress = StopProgress.NONE, isComposing = false,
                followUps = emptyList(), steppedIn = 0, canSend = false, canResend = false,
                isStopRequested = false, recognisedSigns = emptyList(),
            ),
        )
        override val snapshot: StateFlow<CallSnapshot> = state

        override fun run(command: CallCommand): Boolean? = error("the driver never acts on the store")
    }
}
