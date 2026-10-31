package ai.ishara.demo.call

import ai.ishara.demo.core.call.AppMessage
import ai.ishara.demo.core.call.AskChoice
import ai.ishara.demo.core.call.AskOption
import ai.ishara.demo.core.call.Brief
import ai.ishara.demo.core.call.BriefRequest
import ai.ishara.demo.core.call.CallCore
import ai.ishara.demo.core.call.CallMode
import ai.ishara.demo.core.call.CallNotes
import ai.ishara.demo.core.call.CallState
import ai.ishara.demo.core.call.CallStore
import ai.ishara.demo.core.call.CaptionSpeaker
import ai.ishara.demo.core.call.LocalCallSession
import ai.ishara.demo.core.call.Outgoing
import ai.ishara.demo.core.call.ProposalOrigin
import ai.ishara.demo.core.call.ProposalOutcome
import ai.ishara.demo.core.call.ServerMessage
import ai.ishara.demo.core.call.Sign
import ai.ishara.demo.core.call.TranscriptEntry
import ai.ishara.demo.models.CallSetup
import ai.ishara.demo.models.Delegation
import ai.ishara.demo.recognition.CameraState
import ai.ishara.demo.recognition.RecognitionEvent
import ai.ishara.demo.recognition.RecognitionResult
import ai.ishara.demo.recognition.ScriptedRecognitionController
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.io.IOException
import java.util.UUID
import kotlin.math.max

/**
 * Plays the PLAN §1 clinic call on timers so the whole demo can be clicked through without a
 * backend or a real call. It stands in for the backend: it answers the store's messages
 * (chips, approve, stop, end) with the messages the backend would send, so the real Swift
 * `TurnStore` rules apply unchanged. It is the local session's synchronous sink, like
 * iOS's `OutgoingMessageSink`. Use it from the main thread.
 */
class FakeCallDriver(
    private val options: Options = Options(),
    private val stages: List<DemoScript.Stage> = DemoScript.stages,
    /** Plays each stage's signs; null when real recognition runs alongside the fake call. */
    private val recognition: ScriptedRecognitionController? = null,
    private val now: () -> Double = { System.currentTimeMillis() / 1000.0 },
) : CallDriver {
    data class Options(
        /** Multiply every delay; below 1 runs the script faster. */
        val timeScale: Double = 1.0,
        /** Script stages (0-based) whose first approval comes back "not delivered". */
        val undeliveredStages: Set<Int> = emptySet(),
        /** Stages whose first reply the receptionist talks over; it is still delivered. */
        val interruptedStages: Set<Int> = emptySet(),
        /**
         * Lose the backend connection mid-call: on a live call once the first draft is on
         * screen, on a delegated call once the agent has asked its question.
         */
        val connectionDrop: ConnectionDrop? = null,
        /** Delegated call (version B): the receptionist first asks "when?" with no time on offer. */
        val openTimeQuestion: OpenTimeQuestion? = null,
        /** Seconds after a delegated call ends until its notes carry Bolna's own summary. */
        val bolnaSummaryDelay: Double? = null,
    )

    /** How the delegated call's open "when?" question is answered. */
    data class OpenTimeQuestion(
        /** Signed through the scripted recognizer a moment after the question; null leaves it to a tap. */
        val signedAnswer: Sign? = null,
        /** The receptionist's words, as the live transcriber would hand them over. */
        val question: String = DelegatedDemo.OPEN_QUESTION,
    )

    /** How a simulated lost connection plays out, like [LiveCallDriver]'s reconnects. */
    enum class ConnectionDrop(val wire: String) {
        /** The socket comes back and the backend reports the call status again. */
        RECONNECTS("reconnects"),

        /** Every reconnect fails, and the backend stays unreachable (notes too). */
        STAYS_DOWN("staysDown"),
        ;

        companion object {
            fun fromWire(raw: String): ConnectionDrop? = entries.firstOrNull { it.wire == raw }
        }
    }

    private class PendingProposal(
        val turnId: String,
        val text: String,
        val origin: ProposalOrigin,
        val then: () -> Unit,
    )

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var session: LocalCallSession? = null
    private var nextStage = 0
    private val approvedTurns = mutableSetOf<String>()

    /** Counts chips messages; a draft goes out only if no newer chips came in meanwhile. */
    private var chipsRevision = 0
    private val failedStages = mutableSetOf<Int>()
    private var speakingTurn: String? = null
    private var speakingJob: Job? = null
    private val jobs = mutableListOf<Job>()
    private var isOver = false
    private var endedAt: Double? = null

    /** The simulated connection is down: nothing the app sends arrives. */
    private var isDisconnected = false

    // Delegated call (D9), played from DelegatedDemo.
    private var setup: CallSetup? = null
    private val transcript = mutableListOf<TranscriptEntry>()
    private val answers = mutableListOf<String>()
    private var openAskId: String? = null
    private var openOptions: List<AskOption> = emptyList()
    private var hasAsked = false
    private var askTimer: Job? = null

    // Steer call.
    private var isPresent = false
    private var isComposing = false
    private var heldLine: (() -> Unit)? = null
    private var pendingProposal: PendingProposal? = null
    private var proposalJob: Job? = null
    private var fillerIndex = 0
    private var steerStep = 0
    private var steerSteppedIn = 0
    private val steerFollowUps = mutableListOf<String>()
    private val steerSaid = mutableListOf<String>()
    private var steerBooked = false

    /** Runs only when [Options.connectionDrop] is [ConnectionDrop.STAYS_DOWN]. */
    override var onReconnectStopped: ((ReconnectStop) -> Unit)? = null

    // CallDriver

    override suspend fun start(setup: CallSetup): CallStore {
        val session = CallCore.startLocalSession(CallState.DIALING)
        session.sink = ::receiveFromApp
        this.session = session
        this.setup = setup
        val delegation = setup.delegation
        if (delegation != null) {
            if (delegation.mode == CallMode.STEER) playSteer(setup, delegation) else playDelegated(setup, delegation)
            return session
        }
        schedule(1.0) { deliver(ServerMessage.Status(CallState.RINGING)) }
        schedule(2.5) {
            deliver(ServerMessage.Status(CallState.IN_CALL))
            // Turn 0: the agent opens with the disclosure before the user signs.
            deliver(ServerMessage.Caption(DemoScript.DISCLOSURE, now(), CaptionSpeaker.AGENT))
            playNextStage()
        }
        return session
    }

    /** Stops the script and frees the store. Sends nothing. */
    override fun close() {
        finish()
        session?.close()
    }

    override suspend fun createBrief(request: BriefRequest): Brief = DelegatedDemo.brief(request)

    override suspend fun notes(): CallNotes {
        val setup = setup ?: throw CallDriverError.NoCall
        if (isDisconnected) throw IOException("Could not connect to the server.")
        val delegation = setup.delegation
            ?: return CallNotes(callId = "demo-call", mode = CallMode.LIVE, ready = isOver, transcript = transcript.toList())
        var notes = DelegatedDemo.notes(
            goal = delegation.brief.goal,
            name = setup.details.name,
            brief = delegation.brief.text,
            transcript = transcript.toList(),
            answers = answers.toList(),
            ready = isOver,
        )
        if (delegation.mode == CallMode.STEER) {
            notes = notes.copy(mode = CallMode.STEER, steppedIn = steerSteppedIn, followUps = steerFollowUps.toList())
            if (isOver) {
                val booked = if (steerBooked) listOf("They confirmed: \"$STEER_CONFIRMATION\"") else emptyList()
                notes = notes.copy(
                    outcome = if (steerBooked) "booked" else "unclear",
                    summary = notes.summary + steerSaid.map { "You said: \"$it\"" } + booked,
                )
            }
        }
        val delay = options.bolnaSummaryDelay
        val endedAt = endedAt
        if (delay != null && endedAt != null && now() - endedAt >= delay * options.timeScale) {
            notes = notes.copy(bolnaSummary = DelegatedDemo.automaticSummary(delegation.brief.goal, setup.details.name))
        }
        return notes
    }

    // What the backend would receive

    private fun receiveFromApp(item: Outgoing) {
        val message = (item as? Outgoing.Message)?.message ?: return
        if (isOver || isDisconnected) return
        when (message) {
            is AppMessage.Chips -> {
                chipsRevision += 1
                val revision = chipsRevision
                val (text, source) = DemoScript.draft(message.chips)
                schedule(0.5) {
                    // Like the backend's draft_is_current: never a draft for chips that have since changed.
                    if (chipsRevision == revision) deliver(ServerMessage.Draft(message.turnId, text, source))
                }
            }
            is AppMessage.Approve -> approve(message.turnId, message.text)
            AppMessage.Stop -> {
                val turnId = speakingTurn ?: return
                speakingJob?.cancel()
                speakingJob = schedule(0.3) { finishSpeaking(turnId, delivered = false, reason = "stopped") }
            }
            AppMessage.End -> {
                // The agent says goodbye as it hangs up. The store ignores events once it has
                // ended, so the caption goes in now, while `end()` is still on its way.
                say(CaptionSpeaker.AGENT, DemoScript.GOODBYE)
                finish()
            }
            is AppMessage.Answer -> answer(message.askId, message.choice)
            is AppMessage.Presence -> {
                isPresent = message.present
                val pending = pendingProposal
                if (!message.present && pending != null && pending.origin == ProposalOrigin.AGENT) settleProposal(spoken = true)
            }
            is AppMessage.Hold -> hold(message.turnId, message.composing)
            is AppMessage.Say -> sayTyped(message.text)
        }
    }

    // Script

    private fun approve(turnId: String, text: String) {
        // "Send now" on a proposed steer line: its window ends early.
        if (pendingProposal?.turnId == turnId) {
            settleProposal(spoken = true)
            return
        }
        if (setup?.isSteer == true) {
            // A signed line on a steer call: the user stepped in; the agent's line is dropped.
            if (pendingProposal != null) settleProposal(spoken = false)
            isComposing = false
            heldLine = null
            steerSteppedIn += 1
        }
        // Single use per turn id, like the backend.
        if (speakingTurn != null || !approvedTurns.add(turnId)) return
        speakingTurn = turnId
        // Replies arrive later, never inside the store's own SEND.
        schedule(0.0) { deliver(ServerMessage.Status(CallState.SPEAKING)) }
        val stage = nextStage - 1
        val shouldFail = stage in options.undeliveredStages && failedStages.add(stage)
        val duration = max(1.5, text.length * 0.06)
        if (stage in options.interruptedStages) {
            schedule(duration / 2) { deliver(ServerMessage.Caption(INTERRUPTION, now())) }
        }
        speakingJob = schedule(duration) { finishSpeaking(turnId, delivered = !shouldFail) }
    }

    private fun finishSpeaking(turnId: String, delivered: Boolean, reason: String = "no_confirmation") {
        speakingTurn = null
        speakingJob = null
        deliver(if (delivered) ServerMessage.Spoken(turnId) else ServerMessage.NotDelivered(turnId, reason))
        deliver(ServerMessage.Status(CallState.IN_CALL))
        if (delivered) schedule(2.0) { playNextStage() }
    }

    private fun playNextStage() {
        if (nextStage >= stages.size) return
        val stage = stages[nextStage]
        nextStage += 1

        var at = 0.0
        stage.caption?.let { caption ->
            schedule(at) { deliver(ServerMessage.Caption(caption, now())) }
            at += 2.5
        }
        val recognition = recognition ?: return
        if (stage.losesFraming) {
            schedule(at) { recognition.emit(RecognitionEvent.Camera(CameraState.CANT_SEE)) }
            at += 1.5
            schedule(at) { recognition.emit(RecognitionEvent.Camera(CameraState.WATCHING)) }
            at += 1.0
        }
        for (sign in stage.signs) {
            schedule(at) { recognition.sign(sign) }
            at += 2.2
        }
        // The first turn's chips and draft are on screen by now.
        val drop = options.connectionDrop
        if (nextStage == 1 && drop != null) schedule(at) { loseConnection(drop) }
    }

    /**
     * The app's socket goes away. The backend side of the call carries on (the delegated
     * question's timer keeps running), but nothing reaches the app and nothing the app sends
     * arrives, until the socket comes back or the app gives up.
     */
    private fun loseConnection(drop: ConnectionDrop) {
        isDisconnected = true
        session?.connectionLost()
        when (drop) {
            ConnectionDrop.RECONNECTS -> schedule(RECONNECT_DELAY) {
                isDisconnected = false
                // Like the backend on a new socket: the call's status, nothing else.
                deliver(ServerMessage.Status(CallState.IN_CALL))
            }
            ConnectionDrop.STAYS_DOWN -> schedule(RECONNECT_DELAY) { onReconnectStopped?.invoke(ReconnectStop.AttemptsUsedUp) }
        }
    }

    // Delegated script (D9)

    /** Disclosure, the agent's opening from the brief, then the receptionist offers a slot (or asks "when?"). */
    private fun playDelegated(setup: CallSetup, delegation: Delegation) {
        val time = DelegatedDemo.preferredTime(delegation.brief)
        val opening = DelegatedDemo.opening(setup.details.name, delegation.brief.goal, time)
        schedule(1.0) { deliver(ServerMessage.Status(CallState.RINGING)) }
        schedule(2.5) {
            deliver(ServerMessage.Status(CallState.IN_CALL))
            say(CaptionSpeaker.AGENT, DemoScript.DISCLOSURE)
        }
        schedule(4.5) { say(CaptionSpeaker.AGENT, opening) }
        schedule(7.0) {
            val question = options.openTimeQuestion
            if (question != null) askWhen(delegation, time, question) else offerSlot(delegation)
        }
    }

    /** The receptionist offers a time. Attended: the agent asks the user; unattended: it promises a callback. */
    private fun offerSlot(delegation: Delegation) {
        say(CaptionSpeaker.RECEPTIONIST, DelegatedDemo.OFFER)
        if (!delegation.attended) {
            say(CaptionSpeaker.AGENT, DelegatedDemo.CALLBACK_LINE)
            schedule(2.0) { hangUp() }
            return
        }
        ask("demo-ask", DelegatedDemo.OFFER, DelegatedDemo.options)
    }

    /**
     * The receptionist asks "when?" with no time on offer. Attended: the user picks a time word.
     * Unattended: the agent says the brief's time, or promises a callback without one.
     */
    private fun askWhen(delegation: Delegation, time: String?, question: OpenTimeQuestion) {
        say(CaptionSpeaker.RECEPTIONIST, question.question)
        if (!delegation.attended) {
            if (time == null) {
                say(CaptionSpeaker.AGENT, DelegatedDemo.CALLBACK_LINE)
                schedule(2.0) { hangUp() }
                return
            }
            say(CaptionSpeaker.AGENT, DelegatedDemo.timeLine(time))
            schedule(2.5) { offerSlot(delegation) }
            return
        }
        ask("demo-ask-when", question.question, DelegatedDemo.timeOptions)
        val signed = question.signedAnswer
        val recognition = recognition
        if (signed != null && recognition != null) {
            schedule(2.5) { recognition.sign(RecognitionResult.Recognised(signed)) }
        }
    }

    private fun ask(askId: String, question: String, askOptions: List<AskOption>) {
        say(CaptionSpeaker.AGENT, DelegatedDemo.PAUSE_LINE)
        openAskId = askId
        openOptions = askOptions
        deliver(ServerMessage.Ask(askId, question, askOptions, DelegatedDemo.CALLBACK_LINE, DelegatedDemo.ASK_TIMEOUT))
        startAskTimer()
        // The connection drops once, after the call's first question.
        val drop = options.connectionDrop
        if (!hasAsked && drop != null) schedule(DROP_DELAY) { loseConnection(drop) }
        hasAsked = true
    }

    private fun answer(askId: String, choice: AskChoice) {
        if (askId != openAskId) {
            deliver(ServerMessage.Error("unknown_ask", "That question is no longer open."))
            return
        }
        val spoken = openOptions.firstOrNull { it.choice == choice }?.spoken
        if (spoken == null) {
            deliver(ServerMessage.Error("bad_choice", "Not one of the options."))
            return
        }
        askTimer?.cancel()
        resolveOrHold(choice, spoken)
    }

    private fun resolveOrHold(choice: AskChoice, spoken: String) {
        when (choice) {
            AskChoice.WAIT -> {
                // Like the backend: the agent holds the line and the question stays open.
                say(CaptionSpeaker.AGENT, spoken)
                startAskTimer()
            }
            AskChoice.TOMORROW, AskChoice.MORNING, AskChoice.NOW -> {
                // A time word settles nothing: the receptionist then offers a time.
                resolveAsk(spoken, "user")
                val delegation = setup?.delegation ?: return
                schedule(2.0) { offerSlot(delegation) }
            }
            AskChoice.YES, AskChoice.NO -> {
                resolveAsk(spoken, "user")
                val reply = if (choice == AskChoice.YES) DelegatedDemo.CONFIRMATION else DelegatedDemo.DECLINED
                schedule(2.0) {
                    say(CaptionSpeaker.RECEPTIONIST, reply)
                    schedule(1.5) {
                        say(CaptionSpeaker.AGENT, DelegatedDemo.CLOSE_LINE)
                        hangUp()
                    }
                }
            }
        }
    }

    private fun startAskTimer() {
        askTimer = schedule(DelegatedDemo.ASK_TIMEOUT) {
            resolveAsk(DelegatedDemo.CALLBACK_LINE, "timeout")
            schedule(2.0) { hangUp() }
        }
    }

    private fun resolveAsk(spoken: String, source: String) {
        val askId = openAskId ?: return
        openAskId = null
        answers += spoken
        transcript += TranscriptEntry(CaptionSpeaker.AGENT, spoken, now())
        deliver(ServerMessage.AskResolved(askId, spoken, source))
    }

    // Steer script

    /**
     * Disclosure and opening, then a receptionist who offers the wrong time first, then a
     * fitting one, then confirms. Each agent line is proposed while the app is in front.
     */
    private fun playSteer(setup: CallSetup, delegation: Delegation) {
        val opening = DelegatedDemo.opening(setup.details.name, delegation.brief.goal, DelegatedDemo.preferredTime(delegation.brief))
        schedule(1.0) { deliver(ServerMessage.Status(CallState.RINGING)) }
        schedule(2.5) {
            deliver(ServerMessage.Status(CallState.IN_CALL))
            say(CaptionSpeaker.AGENT, DemoScript.DISCLOSURE)
        }
        schedule(4.5) {
            say(CaptionSpeaker.AGENT, opening)
            schedule(2.5) { steerNext() }
        }
    }

    /** The receptionist's next turn and the agent's rule-bound answer to it. */
    private fun steerNext() {
        if (isOver) return
        val step = steerStep
        steerStep += 1
        when (step) {
            0 -> {
                say(CaptionSpeaker.RECEPTIONIST, "We have 4 pm tomorrow. Does that work?")
                agentLine("No, 4 pm tomorrow doesn't work, sorry. Is there anything in the morning?") { steerNext() }
            }
            1 -> {
                say(CaptionSpeaker.RECEPTIONIST, "Let me see. We have 10:30 tomorrow morning.")
                agentLine("Yes, 10:30 tomorrow morning works. Thank you.") { steerNext() }
            }
            2 -> {
                val question = "Can I get the date of birth?"
                say(CaptionSpeaker.RECEPTIONIST, question)
                steerFollowUps += question
                deliver(ServerMessage.FollowUp(question))
                agentLine("I don't have that with me. Could I send it to you afterwards?") { steerNext() }
            }
            else -> {
                say(CaptionSpeaker.RECEPTIONIST, "That's fine. $STEER_CONFIRMATION")
                steerBooked = true
                agentLine(DelegatedDemo.CLOSE_LINE) { hangUp() }
            }
        }
    }

    /** Proposes [text] to a present user (spoken when the window runs out) or says it at once. */
    private fun agentLine(text: String, then: () -> Unit) {
        val continuation = { schedule(2.0) { then() } }
        if (!isPresent || isComposing) {
            schedule(1.5) {
                say(CaptionSpeaker.AGENT, text)
                continuation()
            }
            return
        }
        schedule(1.5) { propose(text, ProposalOrigin.AGENT) { continuation() } }
    }

    private fun propose(text: String, origin: ProposalOrigin, then: () -> Unit) {
        val turnId = "steer-" + UUID.randomUUID().toString().uppercase().take(8)
        // Like the backend: Ishara's line waits a fixed 2 s; the user's preview 1.5 s.
        val window = if (origin == ProposalOrigin.AGENT) 2.0 else 1.5
        pendingProposal = PendingProposal(turnId, text, origin, then)
        deliver(ServerMessage.Proposal(turnId, text, window, origin))
        proposalJob = schedule(window) { settleProposal(spoken = true) }
    }

    private fun settleProposal(spoken: Boolean) {
        val pending = pendingProposal ?: return
        proposalJob?.cancel()
        proposalJob = null
        pendingProposal = null
        deliver(ServerMessage.ProposalResolved(pending.turnId, if (spoken) ProposalOutcome.SPOKEN else ProposalOutcome.HELD))
        if (!spoken) return
        if (pending.origin == ProposalOrigin.AGENT) say(CaptionSpeaker.AGENT, pending.text) else note(pending.text)
        pending.then()
    }

    private fun hold(turnId: String, composing: Boolean) {
        if (composing) {
            isComposing = true
            val pending = pendingProposal
            if (pending != null && pending.turnId == turnId) {
                if (pending.origin == ProposalOrigin.AGENT) {
                    heldLine = {
                        say(CaptionSpeaker.AGENT, pending.text)
                        pending.then()
                    }
                }
                settleProposal(spoken = false)
            }
            // The agent covers the pause with a rotating filler.
            val filler = FILLERS[fillerIndex % FILLERS.size]
            fillerIndex += 1
            schedule(1.0) { say(CaptionSpeaker.AGENT, filler) }
            return
        }
        isComposing = false
        val held = heldLine ?: return
        heldLine = null
        schedule(0.5) { held() }
    }

    private fun sayTyped(text: String) {
        isComposing = false
        heldLine = null
        steerSteppedIn += 1
        // As the backend's tidy() does without an LLM: a capital, and "?" for a question.
        val tidy = text.trim()
        val firstWord = tidy.split(" ").firstOrNull()?.lowercase().orEmpty()
        val ending = when {
            tidy.endsWith(".") || tidy.endsWith("?") -> ""
            firstWord in QUESTION_WORDS -> "?"
            else -> "."
        }
        val polished = tidy.take(1).uppercase() + tidy.drop(1) + ending
        val continuation = {
            schedule(2.0) {
                say(CaptionSpeaker.RECEPTIONIST, "Of course. Let me check that for you.")
                schedule(2.0) { steerNext() }
            }
            Unit
        }
        if (isPresent) {
            propose(polished, ProposalOrigin.USER, continuation)
        } else {
            note(polished)
            continuation()
        }
    }

    /**
     * A user's typed line, spoken by the voice: in the notes' transcript, shown by the store
     * itself (the app captions it as the user's when its preview ends).
     */
    private fun note(text: String) {
        steerSaid += text
        transcript += TranscriptEntry(CaptionSpeaker.AGENT, text, now())
    }

    private fun say(speaker: CaptionSpeaker, text: String) {
        if (isOver) return
        val at = now()
        transcript += TranscriptEntry(speaker, text, at)
        deliver(ServerMessage.Caption(text, at, speaker))
    }

    private fun hangUp() {
        deliver(ServerMessage.Status(CallState.ENDED))
        finish()
    }

    private fun deliver(message: ServerMessage) {
        if (isOver || isDisconnected) return
        session?.receive(message)
    }

    private fun finish() {
        isOver = true
        if (endedAt == null) endedAt = now()
        jobs.forEach(Job::cancel)
        jobs.clear()
    }

    /** Runs [action] after [seconds] (scaled), always later than now, never after the call is over. */
    private fun schedule(seconds: Double, action: () -> Unit): Job {
        val millis = (seconds * options.timeScale * 1000).toLong()
        val job = scope.launch {
            if (millis > 0) delay(millis)
            action()
        }
        jobs += job
        return job
    }

    companion object {
        /** What the receptionist says over the reply in an interrupted stage. */
        const val INTERRUPTION = "Sorry, who's calling?"
        const val DROP_DELAY = 1.5
        const val RECONNECT_DELAY = 3.0
        private const val STEER_CONFIRMATION = "You're booked for 10:30 tomorrow. Please bring an ID."
        private val FILLERS = listOf("One moment, please.", "Just a second, let me check.", "Bear with me a moment.")
        private val QUESTION_WORDS = setOf(
            "can", "could", "would", "will", "is", "are", "do", "does", "what", "when", "where", "how", "why", "any",
        )
    }
}
