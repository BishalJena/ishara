package ai.ishara.demo.call

import ai.ishara.demo.core.call.Caption
import ai.ishara.demo.core.call.Caption.Speaker
import org.junit.Assert.assertEquals
import org.junit.Test

/** What test mode reads aloud on the phone: Ishara's own lines, each once, in order, only while the call is on. */
class TestModeVoiceTest {
    private class RecordingSpeaker : LineSpeaker {
        val events = mutableListOf<String>()

        override fun speak(text: String) {
            events += "speak:$text"
        }

        override fun stop() {
            events += "stop"
        }

        override fun shutdown() {
            events += "shutdown"
        }
    }

    private val speaker = RecordingSpeaker()

    private fun caption(speaker: Speaker, text: String) = Caption(text, at = 0.0, speaker = speaker)

    private val disclosure = caption(Speaker.AGENT, "Hello, I'm calling for a Deaf caller.")
    private val offer = caption(Speaker.RECEPTIONIST, "We have 4 pm tomorrow. Does that work?")
    private val reply = caption(Speaker.USER, "No, sorry, 4 pm doesn't work.")
    private val goodbye = caption(Speaker.AGENT, "Thank you for your time. Goodbye.")

    @Test
    fun readsTheAgentsLinesAndTheUsersSpokenRepliesInOrderButNeverTheReceptionist() {
        val voice = TestModeVoice(speaker, captionsShown = 0)
        voice.update(listOf(disclosure, offer, reply), isCallOver = false)
        assertEquals(listOf("speak:${disclosure.text}", "speak:${reply.text}"), speaker.events)
    }

    @Test
    fun readsEachLineOnceAsTheCaptionsGrow() {
        val voice = TestModeVoice(speaker, captionsShown = 0)
        voice.update(listOf(disclosure), isCallOver = false)
        voice.update(listOf(disclosure), isCallOver = false)
        voice.update(listOf(disclosure, offer), isCallOver = false)
        voice.update(listOf(disclosure, offer, reply), isCallOver = false)
        voice.update(listOf(disclosure, offer, reply), isCallOver = false)
        assertEquals(listOf("speak:${disclosure.text}", "speak:${reply.text}"), speaker.events)
    }

    @Test
    fun linesAlreadyOnScreenWhenTheVoiceStartsAreNotReadAgain() {
        val voice = TestModeVoice(speaker, captionsShown = 2)
        voice.update(listOf(disclosure, offer, reply), isCallOver = false)
        assertEquals(listOf("speak:${reply.text}"), speaker.events)
    }

    @Test
    fun theEndedCallStopsTheVoiceAndNothingIsReadAfter() {
        val voice = TestModeVoice(speaker, captionsShown = 0)
        voice.update(listOf(disclosure), isCallOver = false)
        voice.update(listOf(disclosure, goodbye), isCallOver = true)
        voice.update(listOf(disclosure, goodbye, reply), isCallOver = false)
        assertEquals(listOf("speak:${disclosure.text}", "stop"), speaker.events)
    }

    @Test
    fun closingStopsAndLetsGoOfTheEngineAndNothingIsReadAfter() {
        val voice = TestModeVoice(speaker, captionsShown = 0)
        voice.update(listOf(disclosure), isCallOver = false)
        voice.close()
        voice.update(listOf(disclosure, reply), isCallOver = false)
        assertEquals(listOf("speak:${disclosure.text}", "stop", "shutdown"), speaker.events)
    }
}
