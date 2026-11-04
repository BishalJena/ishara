package ai.ishara.demo.recognition.pipeline

import ai.ishara.demo.core.call.Sign
import ai.ishara.demo.recognition.RecognitionEvent
import ai.ishara.demo.recognition.RecognitionResult
import ai.ishara.demo.recognition.RecognitionTestAssets
import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.util.Collections

/**
 * The whole app path on the debug build's saved clips (ios/Ishara/LocalAssets/SampleSigns, local
 * evaluation only, never committed): ClipFeed → Holistic Landmarker → session and detector →
 * Kaggle layout → LiteRT → open-set matcher → result, exactly as the emulator app runs it.
 *
 * Clips are named `<word>_<anything>` (a sign the bundle may chip) or `none_<anything>` (must
 * never become a chip); `rest` plays first so Get ready can calibrate. Skips without the clips
 * or the models.
 */
@RunWith(AndroidJUnit4::class)
class ClipReplayEndToEndTest {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private val events: MutableList<RecognitionEvent> = Collections.synchronizedList(mutableListOf())

    @After
    fun tearDown() = scope.cancel()

    private fun results() = synchronized(events) { events.filterIsInstance<RecognitionEvent.Result>().map { it.result } }

    private suspend fun eventually(timeoutMs: Long, condition: () -> Boolean): Boolean =
        withTimeoutOrNull(timeoutMs) {
            while (!condition()) delay(50)
            true
        } ?: false

    @Test
    fun savedClipsBecomeTheirChipsAndNegativesNever() = runBlocking {
        RecognitionTestAssets.assumeAppAsset(HolisticLandmarkProvider.MODEL_ASSET, "run download_holistic_model.sh ios/Ishara/LocalAssets")
        RecognitionTestAssets.assumeAppAsset(LiteRTLogitsModel.MODEL_ASSET, "run download_asl_model.sh ios/Ishara/LocalAssets")
        val clips = RecognitionAssets(RecognitionTestAssets.app).sampleClips()
        assumeTrue("no rest clip in SampleSigns (see ios/Ishara/LocalAssets/README.md)", clips.any { it.name == ClipFeed.REST_CLIP_NAME })

        val controller = withContext(Dispatchers.Main) {
            RecognitionPipelines.clips(RecognitionTestAssets.app, scope).also { controller ->
                val flow = controller.signingEvents()
                scope.launch { flow.collect { events += it } }
                controller.start()
            }
        }
        assumeTrue("no sign clips besides rest", controller.replayOptions.isNotEmpty())
        assertTrue("Get ready never finished on the rest clip", eventually(60_000) { controller.getReady.state.value.isReady })
        assertNull(controller.failure.value)

        val outcomes = linkedMapOf<String, List<RecognitionResult>>()
        for (name in controller.replayOptions) {
            val before = results().size
            withContext(Dispatchers.Main) { controller.replay(name) }
            // A clip gives one result at most; wait for it, then for the clip to finish playing.
            eventually(CLIP_TIMEOUT_MS) { results().size > before }
            delay(SETTLE_MS)
            outcomes[name] = results().drop(before)
            Log.i(TAG, "replay $name → ${outcomes[name]}")
        }
        withContext(Dispatchers.Main) { controller.stop() }
        Log.i(TAG, "summary: $outcomes")

        for ((name, results) in outcomes) {
            val word = name.substringBefore('_')
            if (word == "none") {
                assertTrue("$name became a chip: $results", results.none { it is RecognitionResult.Recognised })
            } else {
                val sign = Sign.fromWire(word)
                assertEquals("$name: one sign gives one result", 1, results.size)
                assertEquals("$name", RecognitionResult.Recognised(sign!!), results.single())
            }
        }
    }

    private companion object {
        const val TAG = "IsharaRecognitionE2E"
        const val CLIP_TIMEOUT_MS = 30_000L
        const val SETTLE_MS = 2_000L
    }
}
