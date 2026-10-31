package ai.ishara.demo.recognition

import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assume.assumeTrue
import kotlin.math.ln

/**
 * The app's assets (bundle, models, debug sample clips) and the test APK's fixtures, which the
 * build copies from the iOS packages' own test folders (see `copyRecognitionTestFixtures`).
 */
object RecognitionTestAssets {
    const val DETECTOR_FIXTURES = "RecognitionCore/Tests/RecognitionCoreTests/Fixtures/detector"
    const val RUNTIME_PARITY = "SignPipelineLiteRT/Tests/SignPipelineLiteRTTests/Fixtures/runtime_parity.json"
    const val HOLISTIC_PHOTO = "SignPipelineMediaPipe/TestAssets/male_full_height_hands.jpg"

    val app get() = InstrumentationRegistry.getInstrumentation().targetContext
    private val tests get() = InstrumentationRegistry.getInstrumentation().context

    val bundleJson: String by lazy { app.assets.open("asl-bundle.json").bufferedReader().use { it.readText() } }

    val glosses: List<String> by lazy {
        val array = org.json.JSONObject(bundleJson).getJSONArray("glosses")
        List(array.length()) { array.getString(it) }
    }

    fun fixture(path: String): String = tests.assets.open(path).bufferedReader().use { it.readText() }

    fun fixtureNames(folder: String): List<String> = tests.assets.list(folder).orEmpty().sorted()

    fun openFixture(path: String) = tests.assets.open(path)

    fun hasFixture(path: String): Boolean = runCatching { tests.assets.open(path).close() }.isSuccess

    fun hasAppAsset(name: String): Boolean = name in app.assets.list("").orEmpty()

    /** Skips (with the reason) when an untracked model or test asset was not installed. */
    fun assumeAppAsset(name: String, howToGetIt: String) = assumeTrue("$name is missing: $howToGetIt", hasAppAsset(name))

    /** Logits with [gloss] at probability ≈ [p] and the rest spread evenly. */
    fun logits(gloss: String, p: Double): FloatArray {
        val rest = (1 - p) / (glosses.size - 1)
        return FloatArray(glosses.size) { ln(if (glosses[it] == gloss) p else rest).toFloat() }
    }
}
