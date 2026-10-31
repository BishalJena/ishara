package ai.ishara.demo.call

import ai.ishara.demo.core.call.Caption
import android.content.Context
import android.speech.tts.TextToSpeech

/** Reads text aloud on this phone. Main thread only. */
interface LineSpeaker {
    /** Queued after anything still being read. */
    fun speak(text: String)

    /** Stops the current line and drops the queue. */
    fun stop()

    /** Lets go of the engine; nothing is read after this. */
    fun shutdown()
}

/**
 * Test mode only (the fake call): reads Ishara's side of the scripted call aloud on this phone,
 * so the call can be heard without a phone line. Speaks each line the call voice said, once and
 * in order: the agent's own lines and the user's replies once the call has spoken them (both
 * arrive as captions). Never a draft, a proposal still being previewed, or the receptionist's
 * words. Lines already captioned when the voice starts are not read again (the screen came
 * back). Stops when the call is over or the screen goes. Main thread only.
 */
class TestModeVoice(private val speaker: LineSpeaker, captionsShown: Int) {
    private var heard = captionsShown
    private var isDone = false

    fun update(captions: List<Caption>, isCallOver: Boolean) {
        if (isDone) return
        if (isCallOver) {
            isDone = true
            speaker.stop()
            return
        }
        captions.drop(heard).filter { it.speaker in SPOKEN_BY_ISHARA }.forEach { speaker.speak(it.text) }
        heard = maxOf(heard, captions.size)
    }

    fun close() {
        isDone = true
        speaker.stop()
        speaker.shutdown()
    }

    private companion object {
        val SPOKEN_BY_ISHARA = setOf(Caption.Speaker.AGENT, Caption.Speaker.USER)
    }
}

/**
 * The phone's text-to-speech engine. Lines asked for before the engine is ready wait for it;
 * without a usable engine nothing is read and nothing fails (test mode only, so silence is fine).
 */
class AndroidLineSpeaker(context: Context) : LineSpeaker {
    private enum class State { STARTING, READY, UNAVAILABLE }

    private var state = State.STARTING
    private val waiting = mutableListOf<String>()
    private var nextId = 0

    // The engine may report a failure from inside its constructor, before this is assigned.
    private lateinit var engine: TextToSpeech

    init {
        engine = TextToSpeech(context.applicationContext, ::onInit)
    }

    private fun onInit(status: Int) {
        if (state != State.STARTING) return
        if (status != TextToSpeech.SUCCESS || !::engine.isInitialized) {
            state = State.UNAVAILABLE
            waiting.clear()
            return
        }
        state = State.READY
        waiting.forEach(::read)
        waiting.clear()
    }

    override fun speak(text: String) {
        when (state) {
            State.STARTING -> waiting += text
            State.READY -> read(text)
            State.UNAVAILABLE -> Unit
        }
    }

    private fun read(text: String) {
        engine.speak(text, TextToSpeech.QUEUE_ADD, null, "ishara-line-${nextId++}")
    }

    override fun stop() {
        waiting.clear()
        if (state == State.READY) engine.stop()
    }

    override fun shutdown() {
        waiting.clear()
        state = State.UNAVAILABLE
        if (::engine.isInitialized) engine.shutdown()
    }
}
