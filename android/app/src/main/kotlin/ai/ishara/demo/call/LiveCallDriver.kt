package ai.ishara.demo.call

import ai.ishara.demo.app.AppConfig
import ai.ishara.demo.core.call.Brief
import ai.ishara.demo.core.call.BriefRequest
import ai.ishara.demo.core.call.CallBackend
import ai.ishara.demo.core.call.CallCore
import ai.ishara.demo.core.call.CallNotes
import ai.ishara.demo.core.call.CallState
import ai.ishara.demo.core.call.CallStore
import ai.ishara.demo.core.call.LiveCallSession
import ai.ishara.demo.models.CallSetup
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Job
import kotlinx.coroutines.MainScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.launch
import kotlin.time.Duration
import kotlin.time.Duration.Companion.seconds

/**
 * The real call: `POST /calls` on the Ishara backend, then one WebSocket per call, via
 * CallSession's `LiveCall`. The backend asks Bolna to dial (Path B).
 *
 * When the socket drops, the store goes silent ("Nothing will be sent") and this driver
 * reconnects a few times, waiting longer each time. Nothing from before the drop is resent;
 * the store comes back when the backend reports the call status again. A close the backend
 * meant as a refusal (4401 / 4404 / 4409) is never reconnected.
 */
class LiveCallDriver(
    private val backend: CallBackend,
    private val reconnectDelays: List<Duration> = DEFAULT_RECONNECT_DELAYS,
    private val sleep: suspend (Duration) -> Unit = { delay(it) },
    private val scope: CoroutineScope = MainScope(),
) : CallDriver {
    private var call: LiveCallSession? = null

    /** Kept after [close] so the notes of an ended call can still be fetched. */
    private var lastCallId: String? = null
    private var reconnectsUsed = 0
    private var reconnecting: Job? = null
    private var watching: Job? = null

    override var onReconnectStopped: ((ReconnectStop) -> Unit)? = null

    override suspend fun start(setup: CallSetup): CallStore {
        val call = backend.startCall(setup.startRequest)
        this.call = call
        lastCallId = call.callId
        watching?.cancel()
        watching = scope.launch(start = CoroutineStart.UNDISPATCHED) {
            call.connectionLost.collect { connectionLost(call) }
        }
        return call.store
    }

    override suspend fun createBrief(request: BriefRequest): Brief = backend.createBrief(request)

    override suspend fun notes(): CallNotes {
        val callId = lastCallId ?: throw CallDriverError.NoCall
        return backend.notes(callId)
    }

    override fun close() {
        reconnecting?.cancel()
        reconnecting = null
        watching?.cancel()
        watching = null
        call?.close()
        call = null
    }

    private fun connectionLost(call: LiveCallSession) {
        if (reconnecting != null || this.call !== call) return
        reconnecting = scope.launch {
            val close = call.lastClose()
            ensureActive()
            if (close != null && !close.allowsReconnect) {
                stopReconnecting(ReconnectStop.Refused(close.kind))
                return@launch
            }
            if (reconnectsUsed >= reconnectDelays.size) {
                stopReconnecting(ReconnectStop.AttemptsUsedUp)
                return@launch
            }
            val delay = reconnectDelays[reconnectsUsed]
            reconnectsUsed += 1
            sleep(delay)
            ensureActive()
            reconnecting = null
            if (this@LiveCallDriver.call !== call || call.store.snapshot.value.state != CallState.ERROR) return@launch
            call.connect()
        }
    }

    private fun stopReconnecting(reason: ReconnectStop) {
        reconnecting = null
        onReconnectStopped?.invoke(reason)
    }

    companion object {
        val DEFAULT_RECONNECT_DELAYS = listOf(1.seconds, 2.seconds, 4.seconds)

        /** The real driver for [config], through CallSession in the Swift core. */
        fun live(config: AppConfig): LiveCallDriver {
            CallCore.configureBackend(config.backend)
            return LiveCallDriver(CallCore)
        }
    }
}
