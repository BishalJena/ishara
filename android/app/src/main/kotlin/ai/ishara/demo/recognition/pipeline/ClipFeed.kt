package ai.ishara.demo.recognition.pipeline

import android.content.res.AssetFileDescriptor
import android.content.res.AssetManager
import android.graphics.Bitmap
import android.graphics.Matrix
import android.media.MediaExtractor
import android.media.MediaFormat
import android.media.MediaMetadataRetriever
import android.os.ParcelFileDescriptor
import android.util.Log
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.channels.ReceiveChannel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.io.File

/** A saved sign video, named by its file name without the extension (`hello_01`, `rest`). */
class ReplayClip(val name: String, private val opener: () -> AssetFileDescriptor) {
    fun open(): AssetFileDescriptor = opener()

    override fun toString() = "ReplayClip($name)"

    companion object {
        val extensions = listOf("mp4", "mov", "m4v")

        fun file(file: File) = ReplayClip(file.nameWithoutExtension) {
            AssetFileDescriptor(ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY), 0, file.length())
        }

        /** An uncompressed asset (the build keeps clip extensions uncompressed). */
        fun asset(assets: AssetManager, path: String) = ReplayClip(File(path).nameWithoutExtension) { assets.openFd(path) }
    }
}

/**
 * Saved sign videos played in real time, one at a time, with timestamps shifted so the detector
 * and MediaPipe always see time move forward. Used in the emulator, which has no usable camera.
 * A clip named `rest` (both hands in view, then 2–3 s of hands at rest) plays first so Get ready
 * can calibrate; the others are replayed on demand. Port of `ClipFeed` in ios/Ishara/Recognition/FrameFeed.swift.
 *
 * Frames are never dropped: when the worker is slower than real time, playback waits for it.
 */
class ClipFeed(
    clips: List<ReplayClip>,
    private val scope: CoroutineScope,
    private val decoder: ClipDecoder = MediaClipDecoder,
    private val realTime: Boolean = true,
    private val playerDispatcher: CoroutineDispatcher = Dispatchers.IO,
    private val log: (String) -> Unit = { Log.e(TAG, it) },
) : FrameFeed {
    val clips: List<ReplayClip> = clips.sortedBy { it.name }

    /** Saved videos have no live picture to preview. */
    override val camera: FeedCamera? = null
    override var onFailure: ((Throwable) -> Unit)? = null
    override val replayOptions: List<String> get() = clips.map { it.name }.filter { it != REST_CLIP_NAME }

    private var output: Channel<FeedItem>? = null
    private var queue: Channel<ReplayClip>? = null
    private var player: Job? = null

    /** Where the next clip starts on the feed's clock; only the player touches it. */
    @Volatile
    private var nextStart = 0.0

    override fun items(): ReceiveChannel<FeedItem> {
        stopPlayer()
        val output = Channel<FeedItem>(BUFFERED_FRAMES)
        val queue = Channel<ReplayClip>(Channel.UNLIMITED)
        this.output = output
        this.queue = queue
        clips.firstOrNull { it.name == REST_CLIP_NAME }?.let(queue::trySend)
        player = scope.launch(playerDispatcher) {
            for (clip in queue) play(clip, output)
        }
        return output
    }

    override fun replay(option: String) {
        val clip = clips.firstOrNull { it.name == option } ?: return
        queue?.trySend(clip)
    }

    override fun stop() = stopPlayer()

    private fun stopPlayer() {
        player?.cancel()
        player = null
        queue?.close()
        queue = null
        output?.close()
        output = null
    }

    private suspend fun play(clip: ReplayClip, output: Channel<FeedItem>) {
        val offset = nextStart
        var last = offset
        val started = System.nanoTime()
        try {
            decoder.decode(clip) { frame ->
                val t = offset + frame.timestamp
                last = t
                if (realTime) {
                    val wait = (frame.timestamp * 1000).toLong() - (System.nanoTime() - started) / 1_000_000
                    if (wait > 0) delay(wait)
                }
                output.send(FeedItem.Frame(ShiftedFrame(frame, t)))
            }
        } catch (error: CancellationException) {
            throw error
        } catch (error: Exception) {
            log("replay of ${clip.name} failed: $error")
        }
        output.send(FeedItem.Hold(HOLD_AFTER_CLIP))
        nextStart = last + HOLD_AFTER_CLIP + 1.0 / 30
    }

    companion object {
        const val REST_CLIP_NAME = "rest"

        /** Held after each clip so the detector sees the hands settle and closes the sign. */
        const val HOLD_AFTER_CLIP = 0.8
        private const val BUFFERED_FRAMES = 4
        private const val TAG = "IsharaRecognition"
    }
}

/** A frame of a replayed clip, moved onto the feed's clock. */
private data class ShiftedFrame(val source: VideoFrame, override val timestamp: Double) : VideoFrame {
    override val bitmap: Bitmap get() = source.bitmap
}

/** Decodes a clip's frames in presentation order, upright, with timestamps from the clip's start. */
fun interface ClipDecoder {
    suspend fun decode(clip: ReplayClip, onFrame: suspend (VideoFrame) -> Unit)
}

/**
 * [ClipDecoder] on the platform's MediaExtractor (frame times, without decoding) and
 * MediaMetadataRetriever (frames, decoded a few at a time to bound memory).
 */
object MediaClipDecoder : ClipDecoder {
    private const val BATCH = 8

    override suspend fun decode(clip: ReplayClip, onFrame: suspend (VideoFrame) -> Unit) {
        val times = clip.open().use(::presentationTimes)
        val retriever = MediaMetadataRetriever()
        try {
            clip.open().use { descriptor -> retriever.setDataSource(descriptor.fileDescriptor, descriptor.startOffset, descriptor.length) }
            val frameCount = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_FRAME_COUNT)?.toIntOrNull()
                ?: times.size
            val rotation = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_ROTATION)?.toIntOrNull() ?: 0
            val width = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_WIDTH)?.toIntOrNull() ?: 0
            val count = minOf(frameCount, times.size)
            var index = 0
            while (index < count) {
                val batch = retriever.getFramesAtIndex(index, minOf(BATCH, count - index))
                for (bitmap in batch) {
                    onFrame(BitmapFrame(upright(bitmap, rotation, width), times[index] / 1_000_000.0))
                    index++
                }
            }
        } finally {
            retriever.release()
        }
    }

    /** Sample times of the first video track, sorted into presentation order, in microseconds. */
    private fun presentationTimes(descriptor: AssetFileDescriptor): List<Long> {
        val extractor = MediaExtractor()
        try {
            extractor.setDataSource(descriptor.fileDescriptor, descriptor.startOffset, descriptor.length)
            val track = (0 until extractor.trackCount).firstOrNull {
                extractor.getTrackFormat(it).getString(MediaFormat.KEY_MIME)?.startsWith("video/") == true
            } ?: throw IllegalArgumentException("no video track")
            extractor.selectTrack(track)
            val times = mutableListOf<Long>()
            while (extractor.sampleTime >= 0) {
                times += extractor.sampleTime
                extractor.advance()
            }
            val first = times.minOrNull() ?: 0
            return times.map { it - first }.sorted()
        } finally {
            extractor.release()
        }
    }

    /** Retrievers may hand back frames as stored; turn them upright when the stream is rotated. */
    private fun upright(bitmap: Bitmap, rotation: Int, storedWidth: Int): Bitmap {
        if (rotation % 360 == 0 || bitmap.width != storedWidth) return bitmap
        val rotated = Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, Matrix().apply { postRotate(rotation.toFloat()) }, true)
        bitmap.recycle()
        return rotated
    }
}
