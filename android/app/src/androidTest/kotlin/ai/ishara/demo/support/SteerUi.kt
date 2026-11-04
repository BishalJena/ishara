package ai.ishara.demo.support

import ai.ishara.demo.MainActivity
import ai.ishara.demo.models.UserSettings
import android.Manifest
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.os.Build
import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.hasAnyDescendant
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.ComposeTestRule
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File

/**
 * Drives the steer flow in test mode, like ios/IsharaUITests: the fake call, the real Swift
 * `TurnStore`, screens found by the iOS accessibility identifiers. Pass the instrumentation
 * argument `steerScreenshots true` to also save screenshots of each state (see [shot]).
 */
@OptIn(ExperimentalTestApi::class)
class SteerUi(private val compose: ComposeTestRule) {
    var scenario: ActivityScenario<MainActivity>? = null
        private set

    val context: Context get() = ApplicationProvider.getApplicationContext()

    fun launch(timeScale: String, vararg extras: Pair<String, String>) {
        val intent = Intent(context, MainActivity::class.java)
            .putExtra("IsharaDriver", "fake")
            .putExtra("IsharaCallHistory", "memory")
            .putExtra("IsharaFakeTimeScale", timeScale)
        extras.forEach { (key, value) -> intent.putExtra(key, value) }
        scenario = ActivityScenario.launch(intent)
    }

    fun close() {
        scenario?.close()
        scenario = null
    }

    /** [unmerged]: look inside nodes that read as one element (the proposal bar's label). */
    fun waitFor(tag: String, text: String? = null, timeoutMs: Long = 10_000, unmerged: Boolean = false) {
        if (!unmerged) return compose.waitUntilAtLeastOneExists(matcher(tag, text), timeoutMs)
        compose.waitUntil("$tag shows ${text.orEmpty()}", timeoutMs) {
            compose.onAllNodes(matcher(tag, text), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()
        }
    }

    fun waitForGone(tag: String, text: String? = null, timeoutMs: Long = 10_000) {
        compose.waitUntilDoesNotExist(matcher(tag, text), timeoutMs)
    }

    fun exists(tag: String, text: String? = null): Boolean =
        compose.onAllNodes(matcher(tag, text), useUnmergedTree = false).fetchSemanticsNodes().isNotEmpty()

    /** The tagged node, holding [text] itself (merged) or in one of its rows. */
    private fun matcher(tag: String, text: String?): SemanticsMatcher {
        if (text == null) return hasTestTag(tag)
        val holds = hasText(text, substring = true)
        return hasTestTag(tag) and (holds or hasAnyDescendant(holds))
    }

    /** Saves a full-screen screenshot as `<name>-<light|dark>.png` when screenshots were asked for. */
    fun shot(name: String) {
        val arguments = InstrumentationRegistry.getArguments()
        if (arguments.getString("steerScreenshots") != "true") return
        compose.waitForIdle()
        Thread.sleep(400)
        val night = context.resources.configuration.uiMode and android.content.res.Configuration.UI_MODE_NIGHT_MASK ==
            android.content.res.Configuration.UI_MODE_NIGHT_YES
        val folder = File(context.getExternalFilesDir(null), "steer-screenshots").apply { mkdirs() }
        val bitmap = InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot() ?: return
        File(folder, "$name-${if (night) "dark" else "light"}.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }

    companion object {
        /** The call is placed whatever the answer, but the system prompt would cover the screen. */
        fun grantNotifications() {
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return
            val instrumentation = InstrumentationRegistry.getInstrumentation()
            instrumentation.uiAutomation.grantRuntimePermission(instrumentation.targetContext.packageName, Manifest.permission.POST_NOTIFICATIONS)
        }

        /** Settings start empty, as after a fresh install. */
        fun clearSettings(context: Context) {
            context.getSharedPreferences(UserSettings.PREFERENCES_FILE, Context.MODE_PRIVATE).edit().clear().commit()
        }
    }
}
