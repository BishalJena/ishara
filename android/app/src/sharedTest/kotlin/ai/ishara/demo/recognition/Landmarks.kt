package ai.ishara.demo.recognition

import ai.ishara.demo.recognition.landmarks.ImageSize
import ai.ishara.demo.recognition.landmarks.Landmark
import ai.ishara.demo.recognition.landmarks.LandmarkFrame
import ai.ishara.demo.recognition.pipeline.FeedItem
import ai.ishara.demo.recognition.pipeline.FeedCamera
import ai.ishara.demo.recognition.pipeline.FrameFeed
import ai.ishara.demo.recognition.pipeline.LandmarkProvider
import ai.ishara.demo.recognition.pipeline.VideoFrame
import android.graphics.Bitmap
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.channels.ReceiveChannel
import kotlin.math.roundToInt
import kotlin.math.roundToLong

/**
 * Scripted holistic landmarks: shoulders, face and both hands, with both wrists at `wristY`.
 * Port of `Landmarks` in ios/IsharaTests/Support/RecognitionTestDoubles.swift.
 */
object Landmarks {
    val size = ImageSize(720, 1280)
    const val REST_Y = 0.9f
    const val SIGNING_Y = 0.5f

    /** The rest line calibration gives at [REST_Y]: 0.9 minus the 0.08 margin. */
    const val CALIBRATED_REST_Y = 0.82

    fun frame(
        t: Double,
        wristY: Float = REST_Y,
        body: Boolean = true,
        hands: Boolean = true,
        rightHand: Boolean = true,
    ): LandmarkFrame {
        val pose = MutableList(LandmarkFrame.POSE_COUNT) { Landmark(0.5f, 0.5f, 0f, 0.9f) }
        pose[LandmarkFrame.Pose.LEFT_SHOULDER] = Landmark(0.6f, 0.4f, 0f, if (body) 0.9f else 0.1f)
        pose[LandmarkFrame.Pose.RIGHT_SHOULDER] = Landmark(0.4f, 0.4f, 0f, if (body) 0.9f else 0.1f)
        val face = List(LandmarkFrame.MINIMUM_FACE_COUNT) { i -> Landmark(0.5f + (i % 10) / 1000f, 0.25f, 0f) }
        fun hand(x: Float) = List(LandmarkFrame.HAND_COUNT) { i -> Landmark(x, wristY - i / 200f, 0f) }
        return LandmarkFrame.create(
            timestamp = t, imageSize = size, pose = pose, face = face,
            leftHand = if (hands) hand(0.6f) else null,
            rightHand = if (hands && rightHand) hand(0.4f) else null,
        )
    }

    /** [seconds] of frames at 30 fps starting at [start]. */
    fun run(from: Double, seconds: Double, wristY: Float = REST_Y, body: Boolean = true): List<LandmarkFrame> {
        val count = (seconds * 30).roundToInt()
        return List(count) { frame(t = from + it / 30.0, wristY = wristY, body = body) }
    }

    /** Framing check, 2 s at rest to calibrate, a little rest, then whatever [after] adds. */
    fun calibratedStream(after: (Double) -> List<LandmarkFrame>): List<LandmarkFrame> {
        val setup = run(from = 0.0, seconds = 2.6)
        return setup + after(setup.last().timestamp + 1.0 / 30)
    }

    /** One sign: hands up for [seconds], then 0.6 s back at rest. */
    fun sign(from: Double, seconds: Double = 0.8): List<LandmarkFrame> =
        run(from, seconds, wristY = SIGNING_Y) + run(from + seconds, 0.6)

    /**
     * A one-handed sign: the right hand signs for 0.8 s (the left stays down, untracked), then its
     * hand landmarks vanish for 0.6 s while the pose still puts its wrist at [wristAfter].
     */
    fun oneHandedSign(wristAfterX: Float, wristAfterY: Float): (Double) -> List<LandmarkFrame> = { start ->
        List(42) { index ->
            val signing = index < 24
            val frame = frame(t = start + index / 30.0, wristY = if (signing) SIGNING_Y else REST_Y)
            val pose = frame.pose!!.toMutableList()
            pose[LandmarkFrame.Pose.LEFT_WRIST] = Landmark(0.7f, 1.2f, 0f, 0.1f)
            pose[LandmarkFrame.Pose.RIGHT_WRIST] = if (signing) {
                Landmark(0.4f, SIGNING_Y, 0f, 0.9f)
            } else {
                Landmark(wristAfterX, wristAfterY, 0f, 0.2f)
            }
            frame.with(pose = pose, leftHand = null, rightHand = if (signing) frame.rightHand else null)
        }
    }

    /** Hands up, then the body leaves the frame mid-sign: a lost-tracking rejection. */
    fun lostMidSign(from: Double): List<LandmarkFrame> =
        run(from, 0.5, wristY = SIGNING_Y) +
            run(from + 0.5, 0.7, wristY = SIGNING_Y, body = false) +
            run(from + 1.2, 0.6)

    /** Right hand (pose wrist 16) leaves past the right edge for the second half of the clip. */
    val rightHandLeavesMidSign: List<LandmarkFrame>
        get() = List(30) { index ->
            val inside = index < 12
            val frame = frame(t = index / 30.0, wristY = SIGNING_Y, rightHand = inside)
            if (inside) {
                frame
            } else {
                frame.with(pose = frame.pose!!.toMutableList().also { it[16] = Landmark(1.1f, 0.45f, 0f, 0.2f) })
            }
        }
}

/** A frame with a timestamp and no pixels; scripted providers never read them. */
data class TimedFrame(override val timestamp: Double) : VideoFrame {
    override val bitmap: Bitmap get() = error("scripted frames have no pixels")
}

fun videoFrames(landmarks: List<LandmarkFrame>): List<FeedItem> = landmarks.map { FeedItem.Frame(TimedFrame(it.timestamp)) }

/** Answers with scripted landmarks by frame timestamp (to the millisecond); ignores the pixels. */
class ScriptedLandmarkProvider(frames: List<LandmarkFrame>) : LandmarkProvider {
    private val byTime = frames.associateBy { key(it.timestamp) }

    override fun landmarks(frame: VideoFrame): LandmarkFrame =
        byTime[key(frame.timestamp)] ?: throw IllegalArgumentException("no landmarks at ${frame.timestamp}")

    private fun key(t: Double) = (t * 1000).roundToLong()
}

/** Plays prepared items, then closes. */
class ScriptedFeed(private val prepared: List<FeedItem>, override val camera: FeedCamera? = null) : FrameFeed {
    override var replayOptions: List<String> = emptyList()
    override var onFailure: ((Throwable) -> Unit)? = null
    val replayed = mutableListOf<String>()
    var stopCount = 0
        private set

    override fun items(): ReceiveChannel<FeedItem> {
        val channel = Channel<FeedItem>(Channel.UNLIMITED)
        prepared.forEach { channel.trySend(it) }
        channel.close()
        return channel
    }

    override fun replay(option: String) {
        replayed += option
    }

    override fun stop() {
        stopCount++
    }
}
