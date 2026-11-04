package ai.ishara.demo.recognition.pipeline

import ai.ishara.demo.recognition.BodyOverlay
import ai.ishara.demo.recognition.LiveCamera
import ai.ishara.demo.recognition.core.RecognitionRules
import ai.ishara.demo.recognition.landmarks.LandmarkFrame
import android.graphics.Bitmap
import kotlinx.coroutines.channels.ReceiveChannel
import kotlinx.coroutines.flow.MutableStateFlow

/** A camera or video frame: upright and unmirrored, as recognition reads it. */
interface VideoFrame {
    /** Presentation time in seconds; strictly increasing across everything one feed delivers. */
    val timestamp: Double
    val bitmap: Bitmap
}

data class BitmapFrame(override val bitmap: Bitmap, override val timestamp: Double) : VideoFrame

/**
 * Something the recognition worker processes: a frame, or a pause in which the last landmarks
 * are held (between replayed clips).
 */
sealed interface FeedItem {
    data class Frame(val frame: VideoFrame) : FeedItem

    /** Repeat the last tracked frame for this many seconds, as if the signer held still. */
    data class Hold(val seconds: Double) : FeedItem
}

/** The live camera as a feed exposes it: the controller publishes overlays on it. */
interface FeedCamera : LiveCamera {
    override val overlay: MutableStateFlow<BodyOverlay?>
}

/** Where frames come from: the front camera on a device, saved sign videos in the emulator. */
interface FrameFeed {
    val camera: FeedCamera?
    val replayOptions: List<String>

    /** Called when frames stop for good, for example when the device has no front camera. */
    var onFailure: ((Throwable) -> Unit)?

    /** Starts frames; a later call replaces the previous channel. */
    fun items(): ReceiveChannel<FeedItem>

    fun replay(option: String)

    fun stop()
}

/** Holistic landmarks for one frame. Not thread-safe: one worker uses it. Throws when the frame can't be read. */
fun interface LandmarkProvider {
    fun landmarks(frame: VideoFrame): LandmarkFrame
}

/** The parts of the pipeline that run on the worker; built and closed there. */
class PipelineComponents(
    val landmarks: LandmarkProvider,
    val classifier: SegmentClassifier,
    val rules: RecognitionRules,
    private val release: () -> Unit = {},
) : AutoCloseable {
    override fun close() = release()
}
