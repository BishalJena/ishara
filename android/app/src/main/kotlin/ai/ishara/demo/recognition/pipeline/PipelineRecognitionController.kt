package ai.ishara.demo.recognition.pipeline

import ai.ishara.demo.recognition.BodyOverlay
import ai.ishara.demo.recognition.GetReadyModel
import ai.ishara.demo.recognition.LiveCamera
import ai.ishara.demo.recognition.RecognitionController
import ai.ishara.demo.recognition.RecognitionEvent
import ai.ishara.demo.recognition.RecognitionResult
import ai.ishara.demo.recognition.landmarks.LandmarkFrame
import android.util.Log
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.channels.ReceiveChannel
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.launch
import kotlin.math.floor

/**
 * Real on-device recognition: frames (camera or replayed videos) → holistic landmarks →
 * [RecognitionSession] (checklist, calibration, start/stop detector) → accepted segment →
 * [SegmentClassifier] (ASL Signs model + open-set matcher) → chip. Port of
 * ios/Ishara/Recognition/PipelineRecognitionController.swift.
 *
 * Call it from [scope]'s thread (the main thread in the app). The pipeline runs on
 * [workerDispatcher], one frame at a time; its results come back to [scope].
 */
class PipelineRecognitionController(
    private val feed: FrameFeed,
    private val scope: CoroutineScope,
    notice: String? = null,
    private val workerDispatcher: CoroutineDispatcher = Dispatchers.Default.limitedParallelism(1),
    private val log: (String) -> Unit = { Log.i(TAG, it) },
    private val makeComponents: () -> PipelineComponents,
) : RecognitionController {
    override val getReady = GetReadyModel()

    private val mutableFailure = MutableStateFlow<String?>(null)
    override val failure: StateFlow<String?> = mutableFailure.asStateFlow()
    override val notice: StateFlow<String?> = MutableStateFlow(notice).asStateFlow()

    private var worker: Job? = null
    private var events: Channel<RecognitionEvent>? = null

    init {
        feed.onFailure = { error -> scope.launch { fail(error) } }
    }

    override val camera: LiveCamera? get() = feed.camera
    override val replayOptions: List<String> get() = feed.replayOptions

    override fun start() {
        if (worker != null) return
        val items = feed.items()
        worker = scope.launch {
            val outputs = Channel<WorkerOutput>(Channel.UNLIMITED)
            launch(workerDispatcher) {
                try {
                    val components = try {
                        makeComponents()
                    } catch (error: Exception) {
                        outputs.send(WorkerOutput.Failed(error))
                        return@launch
                    }
                    components.use { process(items, it, log) { output -> outputs.send(output) } }
                } finally {
                    outputs.close()
                }
            }
            for (output in outputs) apply(output)
        }
    }

    override fun signingEvents(): Flow<RecognitionEvent> {
        events?.close()
        val channel = Channel<RecognitionEvent>(Channel.UNLIMITED)
        events = channel
        return channel.receiveAsFlow()
    }

    override fun replay(option: String) = feed.replay(option)

    override fun stop() {
        worker?.cancel()
        worker = null
        feed.stop()
        events?.close()
        events = null
    }

    /** What the worker hands back to [scope]. */
    sealed interface WorkerOutput {
        data class Session(val output: RecognitionSession.Output) : WorkerOutput
        data class Result(val result: RecognitionResult) : WorkerOutput

        /** What the preview draws for the latest camera or video frame. */
        data class Overlay(val overlay: BodyOverlay) : WorkerOutput
        data class Failed(val error: Throwable) : WorkerOutput
    }

    private fun apply(output: WorkerOutput) {
        when (output) {
            is WorkerOutput.Session -> when (val session = output.output) {
                is RecognitionSession.Output.Passed -> getReady.pass(session.check)
                is RecognitionSession.Output.Calibrating -> getReady.recordCalibration(session.seconds)
                is RecognitionSession.Output.CalibrationRestarted -> getReady.restartCalibration()
                is RecognitionSession.Output.Calibrated -> getReady.recordCalibration(GetReadyModel.CALIBRATION_SECONDS)
                is RecognitionSession.Output.Camera -> events?.trySend(RecognitionEvent.Camera(session.state))
                is RecognitionSession.Output.Sign -> Unit // classified on the worker
            }
            is WorkerOutput.Result -> events?.trySend(RecognitionEvent.Result(output.result))
            is WorkerOutput.Overlay -> feed.camera?.overlay?.value = output.overlay
            is WorkerOutput.Failed -> fail(output.error)
        }
    }

    private fun fail(error: Throwable) {
        log("recognition unavailable: ${error.stackTraceToString()}")
        mutableFailure.value = "Recognition can't start: ${error.message ?: error}"
    }

    companion object {
        private const val TAG = "IsharaRecognition"
        private const val HELD_FPS = 30

        /** Runs the whole pipeline over [items] until the feed closes or the coroutine is cancelled. */
        suspend fun process(
            items: ReceiveChannel<FeedItem>,
            components: PipelineComponents,
            log: (String) -> Unit = { Log.i(TAG, it) },
            emit: suspend (WorkerOutput) -> Unit,
        ) {
            RecognitionSession(components.rules).use { session ->
                var last: LandmarkFrame? = null
                for (item in items) {
                    currentCoroutineContext().ensureActive()
                    var tracked: LandmarkFrame? = null
                    val frames: List<LandmarkFrame> = when (item) {
                        is FeedItem.Frame -> {
                            val landmarks = try {
                                components.landmarks.landmarks(item.frame)
                            } catch (error: CancellationException) {
                                throw error
                            } catch (error: Exception) {
                                log("frame skipped: $error")
                                continue
                            }
                            last = landmarks
                            tracked = landmarks
                            listOf(landmarks)
                        }
                        is FeedItem.Hold -> last?.let { held(it, item.seconds) }.orEmpty().also { held ->
                            last = held.lastOrNull() ?: last
                        }
                    }
                    for (frame in frames) {
                        for (output in session.process(frame)) {
                            if (output is RecognitionSession.Output.Sign) {
                                emit(WorkerOutput.Result(components.classifier.classify(output.clip)))
                            } else {
                                emit(WorkerOutput.Session(output))
                            }
                        }
                    }
                    tracked?.let { emit(WorkerOutput.Overlay(it.bodyOverlay(session.restY))) }
                }
            }
        }

        /** The last frame repeated at 30 fps, as if the signer held still. */
        fun held(after: LandmarkFrame, seconds: Double): List<LandmarkFrame> {
            val step = 1.0 / HELD_FPS
            val count = floor(seconds / step + 1e-9).toInt()
            return (1..count).map { after.at(after.timestamp + it * step) }
        }
    }
}
