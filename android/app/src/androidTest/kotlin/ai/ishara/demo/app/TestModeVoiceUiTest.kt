package ai.ishara.demo.app

import ai.ishara.demo.app.AppNavigator.Route
import ai.ishara.demo.call.DemoScript
import ai.ishara.demo.call.LineSpeaker
import ai.ishara.demo.core.call.BackendConfig
import ai.ishara.demo.core.call.CallState
import ai.ishara.demo.core.call.CaptionSpeaker
import ai.ishara.demo.core.call.ServerMessage
import ai.ishara.demo.core.call.onMain
import ai.ishara.demo.models.CallSetup
import ai.ishara.demo.support.RecordingDriver
import ai.ishara.demo.ui.classic.Turns.TURN1
import ai.ishara.demo.ui.theme.IsharaTheme
import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.atomic.AtomicInteger

/**
 * Test mode reads Ishara's side of the scripted call aloud on the phone, and only test mode: the
 * real call screen and the fake call run with a recording speaker in place of the phone's voice.
 */
@OptIn(ExperimentalTestApi::class)
@RunWith(AndroidJUnit4::class)
class TestModeVoiceUiTest {
    @get:Rule
    val compose = createComposeRule()

    private class RecordingSpeaker : LineSpeaker {
        val lines = CopyOnWriteArrayList<String>()
        val stops = AtomicInteger()
        val shutdowns = AtomicInteger()

        override fun speak(text: String) {
            lines += text
        }

        override fun stop() {
            stops.incrementAndGet()
        }

        override fun shutdown() {
            shutdowns.incrementAndGet()
        }
    }

    private val speaker = RecordingSpeaker()
    private val speakersMade = AtomicInteger()

    private fun startClassicCall(options: DemoLaunchOptions, config: Result<AppConfig>, liveDriver: () -> RecordingDriver = { error("no live driver") }) {
        val services = AppServices(
            options.copy(flow = DemoLaunchOptions.Flow.CLASSIC, callHistory = DemoLaunchOptions.CallHistoryLocation.Memory),
            config,
            liveDriver = { liveDriver() },
            testModeSpeaker = {
                speakersMade.incrementAndGet()
                speaker
            },
        )
        val navigator = onMain { AppNavigator(services) }
        compose.setContent { IsharaTheme { AppRoot(navigator) } }
        onMain { navigator.call(CallSetup.demo) }
        compose.waitForIdle()
        onMain { navigator.startFromGetReady((navigator.route as Route.GetReady).recognition, delegated = false) }
    }

    private fun waitForText(tag: String, text: String) =
        compose.waitUntilAtLeastOneExists(hasTestTag(tag) and hasText(text, substring = true), 20_000)

    @Test
    fun theFakeCallReadsIsharasLinesOnceAndADraftOnlyAfterSend() {
        startClassicCall(DemoLaunchOptions(driver = DemoLaunchOptions.Driver.FAKE, fakeTimeScale = 0.5), Result.failure(IllegalStateException("no backend")))

        compose.waitUntil("the disclosure is read", 20_000) { DemoScript.DISCLOSURE in speaker.lines }
        waitForText("call.draft", TURN1)
        compose.waitForIdle()
        assertFalse("a draft was read before SEND", TURN1 in speaker.lines)
        assertFalse("the receptionist was read", speaker.lines.any { it.contains("Does that work?") })

        compose.onNodeWithTag("call.send").performClick()
        compose.waitUntil("the sent reply is read once spoken", 20_000) { TURN1 in speaker.lines }
        assertEquals("a line was read twice: ${speaker.lines}", speaker.lines.toSet().size, speaker.lines.size)

        compose.onNodeWithTag("call.end").performClick()
        compose.waitUntil("End stops the voice", 10_000) { speaker.stops.get() > 0 }
        compose.onNodeWithTag("call.backHome").performClick()
        compose.waitUntil("leaving lets go of the engine", 10_000) { speaker.shutdowns.get() == 1 }
        assertEquals(1, speakersMade.get())
    }

    @Test
    fun aRealCallIsNeverReadAloudOnThePhone() {
        val driver = onMain { RecordingDriver() }
        startClassicCall(
            DemoLaunchOptions(driver = DemoLaunchOptions.Driver.LIVE),
            Result.success(AppConfig(BackendConfig("https://backend.example.test", "test-token"))),
            liveDriver = { driver },
        )
        compose.waitUntil("the call starts", 10_000) { driver.startedWith.isNotEmpty() }
        onMain {
            driver.store.receive(ServerMessage.Status(CallState.IN_CALL))
            driver.store.receive(ServerMessage.Caption(DemoScript.DISCLOSURE, System.currentTimeMillis() / 1000.0, CaptionSpeaker.AGENT))
        }
        waitForText("caption.agent", "Deaf caller")

        compose.onNodeWithTag("call.end").performClick()
        compose.waitForIdle()
        assertEquals("a real call made a phone voice", 0, speakersMade.get())
        assertTrue(speaker.lines.isEmpty())
    }
}
