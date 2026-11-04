package ai.ishara.demo.ui.classic

import ai.ishara.demo.recognition.RecognitionTestAssets
import ai.ishara.demo.recognition.pipeline.ClipFeed
import ai.ishara.demo.recognition.pipeline.HolisticLandmarkProvider
import ai.ishara.demo.recognition.pipeline.LiteRTLogitsModel
import ai.ishara.demo.recognition.pipeline.RecognitionAssets
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.After
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * A real sign video through the whole app in the emulator, like iOS RecognitionReplayUITests:
 * Get ready calibrates on the saved `rest` clip, a sign clip played from the "Replay a sign"
 * menu goes through Holistic → the ASL model → the open-set matcher and becomes a chip, and
 * only SEND speaks its draft on the fake call. Skips without the models or the clips
 * (ios/Ishara/LocalAssets, never committed).
 */
@RunWith(AndroidJUnit4::class)
class RealPipelineCallUiTest {
    @get:Rule
    val compose = createEmptyComposeRule()
    private val app = AppRobot(compose)

    @After
    fun tearDown() = app.close()

    @Test
    fun replayedYesClipBecomesAChipThatOnlySendSpeaks() {
        RecognitionTestAssets.assumeAppAsset(HolisticLandmarkProvider.MODEL_ASSET, "run download_holistic_model.sh ios/Ishara/LocalAssets")
        RecognitionTestAssets.assumeAppAsset(LiteRTLogitsModel.MODEL_ASSET, "run download_asl_model.sh ios/Ishara/LocalAssets")
        val clips = RecognitionAssets(RecognitionTestAssets.app).sampleClips().map { it.name }
        assumeTrue("no rest clip in SampleSigns", ClipFeed.REST_CLIP_NAME in clips)
        val yes = clips.firstOrNull { it.startsWith("yes_") }
        assumeTrue("no yes_ clip in SampleSigns", yes != null)

        app.launch("IsharaRecognition" to "pipeline", timeScale = "1")
        app.waitFor("home.call")
        app.tapPinned("home.call")
        app.waitFor("getReady.start")
        assertFalse("Start was on before calibration", app.isEnabled("getReady.start"))
        // The rest clip plays first: checks, then 2 s of hands at rest.
        app.waitEnabled("getReady.start", 90_000)
        assertTrue(app.exists("getReady.calibration", "calibrated"))
        app.tapPinned("getReady.start")

        app.waitFor("replayMenu")
        compose.onNodeWithTag("replayMenu").performClick()
        app.waitFor("replay.$yes")
        compose.onNodeWithTag("replay.$yes").performClick()

        app.waitFor("chip.yes", timeoutMs = 60_000)
        app.waitFor("call.draft", "\u201C", 20_000)
        val draft = app.text("call.draft").substringAfter('\u201C').substringBefore('\u201D')
        assertTrue("no draft for the chip", draft.isNotBlank())
        assertFalse("a reply was spoken before SEND", app.exists("caption.you"))

        app.sendAndExpectDelivered(draft)
    }
}
