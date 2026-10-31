package ai.ishara.demo.recognition.pipeline

import ai.ishara.demo.recognition.RecognitionTestAssets
import ai.ishara.demo.recognition.landmarks.KaggleLayout
import androidx.test.ext.junit.runners.AndroidJUnit4
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import kotlin.math.abs
import kotlin.math.sin

/**
 * The ASL Signs model on Android's LiteRT against the Mac runtime's logits for a deterministic
 * input (SignPipelineLiteRT's `runtime_parity.json`, the same fixture the iOS test uses).
 */
@RunWith(AndroidJUnit4::class)
class LiteRTLogitsModelTest {
    private lateinit var model: LiteRTLogitsModel

    @Before
    fun load() {
        RecognitionTestAssets.assumeAppAsset(LiteRTLogitsModel.MODEL_ASSET, "run download_asl_model.sh ios/Ishara/LocalAssets")
        model = LiteRTLogitsModel(RecognitionAssets(RecognitionTestAssets.app).mapAsset(LiteRTLogitsModel.MODEL_ASSET))
    }

    @After
    fun close() {
        if (::model.isInitialized) model.close()
    }

    @Serializable
    private data class Fixture(val frames: Int, val logits: List<Float>, val top5: List<Int>)

    @Test
    fun matchesTheMacRuntimeOnTheFixture() {
        val fixture = Json { ignoreUnknownKeys = true }.decodeFromString<Fixture>(RecognitionTestAssets.fixture(RecognitionTestAssets.RUNTIME_PARITY))
        assertEquals(250, model.classCount)

        val logits = model.logits(input(fixture.frames), fixture.frames)

        assertEquals(fixture.logits.size, logits.size)
        val worst = logits.indices.maxOf { abs(logits[it] - fixture.logits[it]) }
        assertTrue("largest logit difference from the Mac runtime: $worst", worst < 1e-3f)
        assertEquals(fixture.top5, logits.indices.sortedByDescending { logits[it] }.take(5))
    }

    @Test
    fun resizesForEachClipLength() {
        for (frames in listOf(8, 40, 8, 1)) {
            assertEquals("$frames frames", 250, model.logits(input(frames), frames).size)
        }
    }

    @Test
    fun rejectsInputThatIsNotWholeFrames() {
        assertThrows(IllegalArgumentException::class.java) { model.logits(floatArrayOf(0f, 1f), 1) }
        assertThrows(IllegalArgumentException::class.java) { model.logits(FloatArray(0), 0) }
    }

    @Test
    fun runsInsideTheLiveBudget() {
        val clip = input(45)
        model.logits(clip, 45)
        val start = System.nanoTime()
        repeat(5) { model.logits(clip, 45) }
        val perClip = (System.nanoTime() - start) / 5 / 1e9
        // 0.1 s on an iPhone; the emulator is slower, so this only guards against a gross regression.
        assertTrue("seconds per 1.5 s clip: $perClip", perClip < 1.0)
    }

    companion object {
        /** x[t,p,c] = 0.5 + 0.3 sin(0.37 t + 0.011 p + 0.5 c); left hand NaN on even t, face NaN at t = 5. */
        fun input(frames: Int): FloatArray {
            val values = FloatArray(frames * KaggleLayout.VALUES_PER_FRAME)
            for (t in 0 until frames) {
                for (p in 0 until KaggleLayout.POINTS) {
                    for (c in 0 until 3) {
                        var value = (0.5 + 0.3 * sin(0.37 * t + 0.011 * p + 0.5 * c)).toFloat()
                        if (t % 2 == 0 && p in 468 until 489) value = Float.NaN
                        if (t == 5 && p < 468) value = Float.NaN
                        values[(t * KaggleLayout.POINTS + p) * 3 + c] = value
                    }
                }
            }
            return values
        }
    }
}
