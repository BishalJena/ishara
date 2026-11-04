package ai.ishara.demo.ui.classic

import ai.ishara.demo.MainActivity
import android.content.Intent
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.getBoundsInRoot
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.ComposeTestRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performScrollToNode
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail

/** The rehearsed call's sentences (`DemoScript`), as iOS `DemoCallUITests` names them. */
object Turns {
    const val TURN1 = "Hello, I'd like a doctor's appointment tomorrow."
    const val TURN3 = "No, sorry, 4 pm doesn't work. Is there anything tomorrow morning?"
    const val TURN5 = "Yes, 10:30 tomorrow morning works. Thank you."

    /** The template draft for no · afternoon · morning. */
    const val THREE_CHIP_DRAFT = "No. In the afternoon, please. In the morning, please."
    const val OFFER = "We have 10:30 tomorrow morning. Does that work?"
    const val CALLBACK_LINE = "I'll need to check that and call back. Thank you."
}

/**
 * Drives the whole app on the device like the iOS UI tests: launches [MainActivity] with launch
 * extras (the fake call, Recent calls in memory) and finds screens by the iOS accessibility
 * identifiers, which the Compose screens use as test tags.
 */
@OptIn(ExperimentalTestApi::class)
class AppRobot(private val compose: ComposeTestRule) {
    private var scenario: ActivityScenario<MainActivity>? = null
    private var changedFontScale = false

    fun launch(vararg extras: Pair<String, String>, timeScale: String = "0.25", flow: String = "classic") {
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("IsharaDriver", "fake")
            .putExtra("IsharaFlow", flow)
            .putExtra("IsharaCallHistory", "memory")
            .putExtra("IsharaFakeTimeScale", timeScale)
        extras.forEach { (key, value) -> intent.putExtra(key, value) }
        scenario = ActivityScenario.launch(intent)
    }

    /** The system font scale (Android's Dynamic Type), restored by [close]. Set before [launch]. */
    fun setFontScale(scale: Float) {
        shell("settings put system font_scale $scale")
        changedFontScale = true
    }

    fun closeApp() {
        scenario?.close()
        scenario = null
    }

    fun close() {
        closeApp()
        if (changedFontScale) shell("settings put system font_scale 1.0")
    }

    private fun shell(command: String) {
        InstrumentationRegistry.getInstrumentation().uiAutomation.executeShellCommand(command).close()
        // The setting reaches the app's configuration asynchronously.
        Thread.sleep(500)
    }

    fun matcher(tag: String, text: String? = null): SemanticsMatcher =
        if (text == null) hasTestTag(tag) else hasTestTag(tag) and hasText(text, substring = true)

    fun waitFor(tag: String, text: String? = null, timeoutMs: Long = 15_000) {
        compose.waitUntilAtLeastOneExists(matcher(tag, text), timeoutMs)
    }

    fun waitGone(tag: String, text: String? = null, timeoutMs: Long = 15_000) {
        compose.waitUntilDoesNotExist(matcher(tag, text), timeoutMs)
    }

    fun exists(tag: String, text: String? = null): Boolean =
        compose.onAllNodes(matcher(tag, text)).fetchSemanticsNodes().isNotEmpty()

    fun count(tag: String, text: String? = null): Int = compose.onAllNodes(matcher(tag, text)).fetchSemanticsNodes().size

    fun isEnabled(tag: String): Boolean {
        val nodes = compose.onAllNodesWithTag(tag).fetchSemanticsNodes()
        return nodes.isNotEmpty() && nodes.first().config.getOrNull(SemanticsProperties.Disabled) == null
    }

    fun waitEnabled(tag: String, timeoutMs: Long = 15_000) {
        compose.waitUntil(timeoutMs) { isEnabled(tag) }
    }

    fun tap(tag: String) {
        compose.onNodeWithTag(tag).performScrollTo().performClick()
    }

    /** Taps a button pinned in a bar (not in a scrolling panel). */
    fun tapPinned(tag: String) {
        compose.onNodeWithTag(tag).performClick()
    }

    /** Checks [condition] keeps holding for [seconds], polling like iOS `assertStays`. */
    fun assertStays(what: String, seconds: Double, condition: () -> Boolean) {
        val end = System.currentTimeMillis() + (seconds * 1000).toLong()
        while (System.currentTimeMillis() < end) {
            compose.waitForIdle()
            if (!condition()) fail("$what didn't hold")
            Thread.sleep(200)
        }
    }

    /** Bounds in dp. */
    fun bounds(tag: String): Rect = compose.onNodeWithTag(tag).getBoundsInRoot().toDpRect()

    private fun androidx.compose.ui.unit.DpRect.toDpRect() = Rect(left.value, top.value, right.value, bottom.value)

    /** [tag] wholly on screen, ending above the top of [above] (iOS `assertFullyVisible`). */
    fun assertFullyVisible(tag: String, above: String) {
        val element = bounds(tag)
        val button = bounds(above)
        val screen = compose.onRoot().getBoundsInRoot().toDpRect()
        assertTrue("$tag $element starts off screen", element.top >= screen.top)
        assertTrue("$tag $element runs into $above $button", element.bottom <= button.top + 0.5f)
        assertTrue("$above $button is off screen", button.bottom <= screen.bottom + 0.5f)
    }

    /** A caption somewhere in the history, scrolled to (the history is a lazy list). */
    fun captionExists(tag: String, text: String): Boolean = runCatching {
        compose.onNodeWithTag("call.captions").performScrollToNode(matcher(tag, text))
    }.isSuccess

    // Steps

    /** Home → Get ready → Start, once Get ready's checks have passed. */
    fun startCall() {
        waitFor("home.call")
        assertTrue("the calling-number note is missing on Home", exists("callingNumberNote"))
        tapPinned("home.call")
        waitFor("getReady.start")
        waitEnabled("getReady.start", 20_000)
        assertTrue("the calling-number note is missing on Get ready", exists("callingNumberNote"))
        tapPinned("getReady.start")
    }

    fun waitForDraft(text: String, timeoutMs: Long = 20_000) = waitFor("call.draft", text, timeoutMs)

    fun sendAndExpectDelivered(text: String) {
        waitEnabled("call.send")
        tapPinned("call.send")
        waitFor("call.deliveryBanner", "Delivered", 20_000)
        assertTrue("the reply isn't in the captions as spoken", captionExists("caption.you", text))
    }

    /** Home → Get ready → Brief, taps tomorrow and morning, builds the brief. */
    fun prepareBrief(expecting: String = "Preferred: tomorrow in the morning.") {
        waitFor("home.callForMe")
        tapPinned("home.callForMe")
        waitFor("getReady.start")
        waitEnabled("getReady.start", 20_000)
        tapPinned("getReady.start")
        waitFor("brief.add.tomorrow")
        assertFalse("nothing to approve before the brief is built", exists("brief.approve"))
        tap("brief.add.tomorrow")
        tap("brief.add.morning")
        assertTrue(exists("chip.tomorrow"))
        tapPinned("brief.prepare")
        waitFor("brief.text", expecting)
    }

    fun setAttended(attended: Boolean) {
        val node = compose.onNodeWithTag("brief.attended").performScrollTo()
        val on = node.fetchSemanticsNode().config.getOrNull(SemanticsProperties.ToggleableState) == androidx.compose.ui.state.ToggleableState.On
        if (on != attended) node.performClick()
        compose.waitUntil(5_000) {
            compose.onNodeWithTag("brief.attended").fetchSemanticsNode().config
                .getOrNull(SemanticsProperties.ToggleableState) == if (attended) androidx.compose.ui.state.ToggleableState.On else androidx.compose.ui.state.ToggleableState.Off
        }
    }

    fun approve() {
        waitFor("brief.approve")
        tapPinned("brief.approve")
    }

    fun openNotes(timeoutMs: Long = 40_000) {
        waitFor("call.notes", timeoutMs = timeoutMs)
        tapPinned("call.notes")
    }

    /** The text shown on a node and its merged children. */
    fun text(tag: String, containing: String? = null): String {
        val config = compose.onNode(matcher(tag, containing)).fetchSemanticsNode().config
        val texts = config.getOrNull(SemanticsProperties.Text).orEmpty().joinToString(" ") { it.text }
        val description = config.getOrNull(SemanticsProperties.ContentDescription).orEmpty().joinToString(" ")
        return "$texts $description"
    }

    fun assertCount(expected: Int, tag: String, text: String) = assertEquals("$tag with \u201C$text\u201D", expected, count(tag, text))
}
