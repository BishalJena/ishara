package ai.ishara.demo.recognition

import ai.ishara.demo.core.call.Sign
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.launch

/**
 * Recognition that replays fixed results instead of watching the camera: for the fake demo
 * call, for UI tests, and for trying the backend without models.
 *
 * Get ready ticks on timers. Results come from [emit] (the fake call plays its script through
 * it), from [script] (played once when signing starts), or from [replay], which the replay
 * menu calls with a sign name or "?". Use it from the main thread.
 */
class ScriptedRecognitionController(
    /** Results played in order, about 2 s apart, once signing starts. */
    private val script: List<RecognitionResult> = emptyList(),
    /** List every sign, "?", "frame" and a "did you mean" candidate per rehearsed sign. */
    offersReplay: Boolean = false,
    private val timeScale: Double = 1.0,
    private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Main),
) : RecognitionController {
    override val getReady = GetReadyModel()
    override val failure: StateFlow<String?> = MutableStateFlow<String?>(null).asStateFlow()
    override val notice: StateFlow<String?> = MutableStateFlow<String?>(null).asStateFlow()

    /** Nothing watches the camera here, so there is no live picture to preview. */
    override val camera: LiveCamera? = null
    override val replayOptions: List<String> = if (offersReplay) allReplayOptions else emptyList()

    private var events: Channel<RecognitionEvent>? = null
    private val jobs = mutableListOf<Job>()
    private var checking: Job? = null

    override fun start() {
        if (checking != null) return
        checking = scope.launch { getReady.runSimulatedChecks(timeScale) }
    }

    override fun signingEvents(): Flow<RecognitionEvent> {
        events?.close()
        val channel = Channel<RecognitionEvent>(Channel.UNLIMITED)
        events = channel
        if (script.isNotEmpty()) {
            jobs += scope.launch {
                for (result in script) {
                    pause(2.0)
                    sign(result)
                }
            }
        }
        return channel.receiveAsFlow()
    }

    override fun replay(option: String) {
        RecognitionResult.fromReplayOption(option)?.let(::sign)
    }

    /** Shows the yellow pill, then the result, then green again. */
    fun sign(result: RecognitionResult) {
        emit(RecognitionEvent.Camera(CameraState.SIGNING))
        jobs += scope.launch {
            pause(1.2)
            emit(RecognitionEvent.Result(result))
            emit(RecognitionEvent.Camera(CameraState.WATCHING))
        }
    }

    fun emit(event: RecognitionEvent) {
        events?.trySend(event)
    }

    override fun stop() {
        checking?.cancel()
        checking = null
        jobs.forEach(Job::cancel)
        jobs.clear()
        events?.close()
        events = null
    }

    private suspend fun pause(seconds: Double) = delay((seconds * timeScale * 1000).toLong())

    companion object {
        /** "?" and "frame" first: a long menu scrolls, and those are what a safety-rule test needs. */
        val allReplayOptions: List<String> = listOf(RecognitionResult.UNSURE_OPTION, RecognitionResult.FRAMING_OPTION) +
            Sign.entries.map { it.wire } + Sign.rehearsed.map { "${it.wire}?" }
    }
}
