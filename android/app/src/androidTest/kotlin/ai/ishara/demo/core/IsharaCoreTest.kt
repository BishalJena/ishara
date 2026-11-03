package ai.ishara.demo.core

import android.os.Looper
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONArray
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import kotlin.math.ln

@RunWith(AndroidJUnit4::class)
class IsharaCoreTest {
    private val bundleJson: String by lazy {
        InstrumentationRegistry.getInstrumentation().targetContext.assets
            .open("asl-bundle.json").bufferedReader().use { it.readText() }
    }
    private val goodQuality = """{"poseFraction":1.0,"handFraction":0.9}"""

    private val subscriptions = mutableListOf<AutoCloseable>()

    @After
    fun unsubscribe() {
        subscriptions.forEach(AutoCloseable::close)
    }

    @Test
    fun versionNamesTheCore() {
        assertTrue(IsharaCore.version().startsWith("IsharaCore "))
    }

    @Test
    fun echoOnMainIsDeliveredFromTheMainThread() {
        data class Delivery(val json: String, val onMainLooper: Boolean)
        val deliveries = LinkedBlockingQueue<Delivery>()
        subscriptions += CoreEvents.subscribe("echo") { event ->
            deliveries.add(Delivery(event.toString(), Looper.myLooper() == Looper.getMainLooper()))
        }
        val message = "héllo \uD83D\uDC4B \"quoted\""

        IsharaCore.echoOnMain(message)

        val delivery = deliveries.poll(5, TimeUnit.SECONDS)
        assertNotNull("no echo within 5 s: is the main-queue pump installed?", delivery)
        val event = JSONObject(delivery!!.json)
        assertEquals(message, event.getString("echo"))
        assertTrue("Swift saw a non-main thread", event.getBoolean("onMainThread"))
        assertTrue("listener ran off the main looper", delivery.onMainLooper)
    }

    @Test
    fun confidentVocabularyWordIsAChip() {
        val result = match(logits(mapOf("tomorrow" to 0.72, "yourself" to 0.1)))

        assertEquals("chip", result.getString("kind"))
        assertEquals("tomorrow", result.getString("label"))
        assertEquals(0.72, result.getDouble("p"), 1e-4)
        assertEquals("tomorrow", result.getJSONArray("top").getJSONObject(0).getString("gloss"))
    }

    @Test
    fun flatOutputIsUnsure() {
        val glossCount = JSONObject(bundleJson).getJSONArray("glosses").length()

        val result = match(JSONArray(List(glossCount) { 0.0 }))

        assertEquals("unsure", result.getString("kind"))
        assertTrue(result.getString("reason").startsWith("not in vocabulary: "))
    }

    @Test(expected = IllegalArgumentException::class)
    fun invalidBundleThrows() {
        IsharaCore.matchLogits("""{"version": 1}""", "[]", goodQuality)
    }

    private fun match(logits: JSONArray) =
        JSONObject(IsharaCore.matchLogits(bundleJson, logits.toString(), goodQuality))

    /** Logits whose softmax gives the named glosses these probabilities; the rest share the remainder. */
    private fun logits(mass: Map<String, Double>): JSONArray {
        val glosses = JSONObject(bundleJson).getJSONArray("glosses")
        val rest = (1.0 - mass.values.sum()) / (glosses.length() - mass.size)
        return JSONArray((0 until glosses.length()).map { ln(mass[glosses.getString(it)] ?: rest) })
    }
}
