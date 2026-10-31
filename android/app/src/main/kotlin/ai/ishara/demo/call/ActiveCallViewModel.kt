package ai.ishara.demo.call

import ai.ishara.demo.core.call.CallCoreException
import ai.ishara.demo.core.call.CallMode
import ai.ishara.demo.core.call.CallSnapshot
import ai.ishara.demo.core.call.CallSocketClose
import ai.ishara.demo.core.call.CallState
import ai.ishara.demo.core.call.Caption
import ai.ishara.demo.core.call.Chip
import ai.ishara.demo.core.call.OpenQuestion
import ai.ishara.demo.core.call.Proposal
import ai.ishara.demo.core.call.QuickReply
import ai.ishara.demo.core.call.SendingPhase
import ai.ishara.demo.core.call.ServerError
import ai.ishara.demo.core.call.Sign
import ai.ishara.demo.core.call.StopProgress
import ai.ishara.demo.core.call.CallStore
import ai.ishara.demo.core.call.AskChoice
import ai.ishara.demo.models.CallRecord
import ai.ishara.demo.models.CallSetup
import ai.ishara.demo.models.DraftBadge
import ai.ishara.demo.models.DraftDisplay
import ai.ishara.demo.recognition.CameraState
import ai.ishara.demo.recognition.RecognitionController
import ai.ishara.demo.recognition.RecognitionEvent
import ai.ishara.demo.recognition.RecognitionResult
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.launch
import java.util.UUID

/**
 * What the Active call screens show, and the buttons they offer.
 *
 * The SEND safety rules live in CallSession's `TurnStore`, the single source of truth for a
 * call; this class only maps the store's snapshot and recognition onto the screens:
 * - recognised signs become chips, unsure ones [?] chips (the store never sends those);
 * - SEND approves the shown draft once, or re-offers a not-delivered reply on a new turn;
 * - STOP, Clear, quick replies and End go straight to the store.
 *
 * Its state is Compose state; use it from the main thread. [scope] mirrors the store's
 * snapshots into that state for as long as the call screen's model lives.
 */
class ActiveCallViewModel(
    val setup: CallSetup,
    val driver: CallDriver,
    val recognition: RecognitionController,
    private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate),
    now: () -> Double = { System.currentTimeMillis() / 1000.0 },
) {
    sealed interface Phase {
        data class Connecting(val state: CallState) : Phase

        data object Live : Phase

        /** The connection dropped; nothing will be sent. It may come back. */
        data class Interrupted(val notice: String) : Phase

        /** The connection is gone and won't be reconnected; only End is left. */
        data class Disconnected(val reason: String) : Phase

        data class Ended(val reason: EndReason) : Phase
    }

    sealed interface EndReason {
        data object UserEnded : EndReason

        /** The user ended the call but the backend couldn't confirm the hang-up. */
        data object HangUpUnconfirmed : EndReason

        data object RemoteEnded : EndReason

        data class Failed(val message: String) : EndReason
    }

    sealed interface Delivery {
        data object Idle : Delivery

        data class Speaking(val text: String) : Delivery

        data object Delivered : Delivery

        /** Spoken although the user tapped STOP. */
        data object DeliveredDespiteStop : Delivery

        data class NotDelivered(val text: String) : Delivery

        /** The user stopped it before it was spoken. */
        data class Stopped(val text: String) : Delivery
    }

    var store: CallStore? by mutableStateOf(null)
        private set

    /** The store's latest snapshot, as Compose state. */
    var snapshot: CallSnapshot? by mutableStateOf(null)
        private set

    var cameraState: CameraState by mutableStateOf(CameraState.WATCHING)
        private set

    var startFailure: String? by mutableStateOf(null)
        private set

    var reconnectStop: ReconnectStop? by mutableStateOf(null)
        private set

    /**
     * D8 pick-one: the latest grey-zone sign, offered as "Did you mean …?" until the user
     * taps it, dismisses it, or the next sign replaces it. Never a chip by itself.
     */
    var candidate: Sign? by mutableStateOf(null)
        private set

    /** The last sign couldn't be read because a hand left the picture. */
    var showsFramingHint: Boolean by mutableStateOf(false)
        private set

    private var userEnded by mutableStateOf(false)
    private var mirroring: Job? = null

    /** This call's id in Recent calls. */
    val recordId: String = UUID.randomUUID().toString().uppercase()
    private val placedAt = now()

    init {
        driver.onReconnectStopped = { reason -> reconnectStop = reason }
    }

    // Derived state

    val phase: Phase
        get() {
            startFailure?.let { return Phase.Ended(EndReason.Failed(it)) }
            val snapshot = snapshot
                ?: return if (userEnded) Phase.Ended(EndReason.UserEnded) else Phase.Connecting(CallState.DIALING)
            // The store's snapshot of its own `end()` lands a moment after End was tapped.
            if (userEnded && snapshot.state != CallState.ENDED) return Phase.Ended(EndReason.UserEnded)
            return when (snapshot.state) {
                CallState.DIALING, CallState.RINGING -> Phase.Connecting(snapshot.state)
                CallState.IN_CALL, CallState.SPEAKING -> Phase.Live
                CallState.ERROR -> reconnectStop?.let { Phase.Disconnected(describe(it)) }
                    ?: Phase.Interrupted(snapshot.notice ?: DISCONNECTED_NOTICE)
                CallState.ENDED -> when {
                    !userEnded -> Phase.Ended(EndReason.RemoteEnded)
                    snapshot.lastError?.code == END_FAILED -> Phase.Ended(EndReason.HangUpUnconfirmed)
                    else -> Phase.Ended(EndReason.UserEnded)
                }
            }
        }

    val isEnded: Boolean get() = phase is Phase.Ended

    /** The call is over for good (ended, or the connection won't come back). */
    val isCallOver: Boolean get() = phase.let { it is Phase.Ended || it is Phase.Disconnected }

    /** D9: the agent pursues an approved brief; the user only answers its questions. */
    val isDelegated: Boolean get() = setup.delegation != null

    /** The agent runs the call and the user may step in by typing or signing. */
    val isSteer: Boolean get() = setup.isSteer

    /** D9 attended: the user watches and answers the agent's questions by sign or tap. */
    val isAttended: Boolean get() = setup.delegation?.attended ?: false

    /** Signs matter on a live call, an attended delegated call (to answer) and a steer call (to step in). */
    val watchesSigns: Boolean get() = !isDelegated || isAttended || isSteer

    // Steer call

    val proposal: Proposal? get() = snapshot?.proposal
    val followUps: List<String> get() = snapshot?.followUps.orEmpty()
    val steppedIn: Int get() = snapshot?.steppedIn ?: 0

    /** The user is typing or signing; the agent only covers the pause. */
    val isSteppingIn: Boolean get() = snapshot?.isComposing ?: false

    /** The call screen came to the front (or left it) on an unlocked phone. */
    fun setPresent(present: Boolean) {
        store?.setPresent(present)
    }

    /** "Send now" on the proposed line. */
    fun approveProposal() {
        store?.approveProposal()
    }

    /** The user tapped into the text field or made a first sign. */
    fun beginSteppingIn() {
        store?.startComposing()
    }

    /** The user left the field empty and dismissed the keyboard. */
    fun cancelSteppingIn() {
        store?.stopComposing()
    }

    /** A typed line, to be polished, previewed and spoken. */
    fun say(text: String) {
        store?.say(text)
    }

    /** Edit the previewed typed line instead of letting it be spoken. */
    fun editPreview() {
        store?.holdPreview()
    }

    /** What Recent calls keeps once the call is over; null while it's on, or if it was never placed. */
    val record: CallRecord?
        get() {
            if (!isCallOver || store == null) return null
            return CallRecord(
                id = recordId,
                date = placedAt,
                contactName = setup.contact.name,
                contactNumber = setup.contact.phoneNumber,
                mode = if (isDelegated) CallMode.DELEGATED else CallMode.LIVE,
                captions = captions.map(CallRecord::Line),
            )
        }

    val connectedAt: Double? get() = snapshot?.connectedAt
    val captions: List<Caption> get() = snapshot?.captions.orEmpty()
    val chips: List<Chip> get() = snapshot?.chips.orEmpty()
    val isStopRequested: Boolean get() = snapshot?.isStopRequested ?: false

    val delivery: Delivery
        get() = when (val sending = snapshot?.sending ?: SendingPhase.Idle) {
            SendingPhase.Idle -> Delivery.Idle
            is SendingPhase.Speaking -> Delivery.Speaking(sending.text)
            SendingPhase.Delivered -> Delivery.Delivered
            SendingPhase.DeliveredDespiteStop -> Delivery.DeliveredDespiteStop
            is SendingPhase.NotDelivered -> Delivery.NotDelivered(sending.text)
            is SendingPhase.Stopped -> Delivery.Stopped(sending.text)
        }

    val isSpeaking: Boolean get() = delivery is Delivery.Speaking

    /** STOP was refused: the reply was already being spoken. */
    val isStopTooLate: Boolean get() = snapshot?.stopProgress == StopProgress.TOO_LATE

    /**
     * A short message for the latest backend error while the call is on. A too-late STOP and
     * a failed hang-up have their own places on screen, so they aren't repeated here.
     */
    val errorMessage: String?
        get() {
            if (isEnded) return null
            return snapshot?.lastError?.let(::describe)
        }

    /**
     * The unspoken sentence (not delivered, or stopped) SEND would offer again: only while
     * the user hasn't started a new reply, so SEND never resends old text over new chips.
     */
    val retryText: String?
        get() {
            val snapshot = snapshot ?: return null
            if (!snapshot.canResend || snapshot.chips.isNotEmpty() || snapshot.draft != null) return null
            return snapshot.unspokenText
        }

    val draft: DraftDisplay?
        get() {
            snapshot?.draft?.let { return DraftDisplay(it.text, DraftBadge.of(it.origin)) }
            val retry = retryText ?: return null
            return DraftDisplay(retry, if (delivery is Delivery.Stopped) DraftBadge.STOPPED else DraftBadge.NOT_DELIVERED)
        }

    /** Recognised chips are on screen and their draft is still being written. */
    val isComposing: Boolean
        get() {
            val snapshot = snapshot ?: return false
            return snapshot.recognisedSigns.isNotEmpty() && snapshot.draft == null
        }

    val canSend: Boolean
        get() {
            val snapshot = snapshot ?: return false
            return snapshot.canSend || retryText != null
        }

    /** The delivery result shows until the user starts the next reply. */
    val showsDeliveryResult: Boolean get() = chips.isEmpty() && snapshot?.draft == null

    val canUseQuickReplies: Boolean get() = phase == Phase.Live && !isSpeaking

    // Lifecycle

    /**
     * Places the call, then turns recognition results into chips until the screen goes away
     * (the calling coroutine is cancelled).
     */
    suspend fun run() = coroutineScope {
        // Subscribe before placing the call so no recognition event falls in between.
        val events = recognition.signingEvents()
        launch(start = CoroutineStart.UNDISPATCHED) { events.collect(::handle) }
        start()
    }

    suspend fun start() {
        if (store != null || startFailure != null) return
        try {
            attach(driver.start(setup))
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            if (!userEnded) startFailure = describeStartFailure(e)
        }
    }

    /** Shows this store's call. If the user already tapped End while it was being placed, it is ended at once. */
    fun attach(store: CallStore) {
        this.store = store
        snapshot = store.snapshot.value
        mirroring?.cancel()
        mirroring = scope.launch(start = CoroutineStart.UNDISPATCHED) {
            store.snapshot.collect { snapshot = it }
        }
        if (userEnded) store.end()
    }

    fun handle(event: RecognitionEvent) {
        if (isEnded) return
        val result = when (event) {
            is RecognitionEvent.Camera -> {
                cameraState = event.state
                return
            }
            is RecognitionEvent.Result -> event.result
        }
        if (!watchesSigns) return
        candidate = null
        showsFramingHint = false
        when (result) {
            is RecognitionResult.Recognised -> accept(result.sign)
            is RecognitionResult.Candidate -> candidate = result.sign
            RecognitionResult.Unsure -> addUnsure()
            RecognitionResult.HandLeftFrame -> {
                showsFramingHint = true
                addUnsure()
            }
        }
    }

    /** The user tapped "Did you mean …?": the candidate counts as signed. */
    fun acceptCandidate() {
        val sign = candidate ?: return
        if (isEnded) return
        candidate = null
        accept(sign)
    }

    fun dismissCandidate() {
        candidate = null
    }

    private fun accept(sign: Sign) {
        // D9: while the agent waits for an answer, a signed option word answers it.
        if (store?.answerIfAsked(sign) == true) return
        // On a delegated call nothing is composed; only answers reach the call. On a steer
        // call a sign is the user stepping in: the agent's proposed line is held first.
        if (isDelegated && !isSteer) return
        if (isSteer) store?.startComposing()
        store?.add(Chip.recognised(sign))
    }

    private fun addUnsure() {
        if (isDelegated && !isSteer) return
        store?.add(Chip.unsure())
    }

    /** Called when the user leaves the screen. Nothing is sent. */
    fun leave() {
        driver.close()
        recognition.stop()
    }

    // User actions

    fun removeChip(chip: Chip) {
        store?.remove(chip)
    }

    /** The agent's open question on an attended delegated call (D9), if any. */
    val openQuestion: OpenQuestion? get() = snapshot?.openQuestion

    fun answer(choice: AskChoice) {
        store?.answer(choice)
    }

    fun clear() {
        store?.clear()
    }

    fun choose(reply: QuickReply) {
        if (!canUseQuickReplies) return
        store?.useQuickReply(reply)
    }

    fun send() {
        val store = store ?: return
        if (snapshot?.canSend == true) {
            store.send()
        } else if (retryText != null) {
            store.resend()
        }
    }

    fun stop() {
        store?.stop()
    }

    fun end() {
        if (isEnded) return
        userEnded = true
        store?.end()
        cameraState = CameraState.WATCHING
        candidate = null
    }

    companion object {
        const val CONNECTION_LOST_TITLE = "Connection lost"

        /** CallSession's `TurnStore.disconnectedNotice`. */
        const val DISCONNECTED_NOTICE = "Nothing will be sent"

        /** CallSession's `ServerError.cannotInterrupt` / `endFailed`. */
        const val CANNOT_INTERRUPT = "cannot_interrupt"
        const val END_FAILED = "end_failed"

        fun describeStartFailure(error: Exception): String {
            val core = error as? CallCoreException
            val status = core?.status
            return when {
                status == 401 -> "The app token was refused. Check the app configuration."
                status == 403 -> "This contact isn't on the backend's allowed list."
                status != null -> "The backend couldn't start the call (HTTP $status)."
                core?.kind == CallCoreException.Kind.NOT_HTTP_RESPONSE -> "The backend couldn't be reached."
                else -> "The call couldn't start: ${error.message}"
            }
        }

        private fun describe(error: ServerError): String? = when (error.code) {
            CANNOT_INTERRUPT, END_FAILED -> null
            "stale_turn" -> "That reply was out of date, so it wasn't sent."
            "already_approved" -> "That reply was already sent."
            "busy_speaking" -> "Wait until the current reply has been spoken."
            "call_not_live" -> "The call isn't connected yet. Nothing was sent."
            "call_ended" -> "The call has ended. Nothing will be sent."
            "bad_message" -> "The backend didn't understand the app. Nothing was sent."
            else -> "Something went wrong on the backend."
        }

        private fun describe(stop: ReconnectStop): String = when (stop) {
            is ReconnectStop.Refused -> when (stop.close) {
                CallSocketClose.UNAUTHORIZED -> "The backend refused the app token"
                CallSocketClose.UNKNOWN_CALL -> "The backend no longer knows this call"
                CallSocketClose.REPLACED -> "This call is now connected somewhere else"
                CallSocketClose.DROPPED -> "The connection couldn't be restored"
            }
            ReconnectStop.AttemptsUsedUp -> "The connection couldn't be restored"
        }
    }
}

/**
 * What the call screen is showing. The scrolling panel and the action bar both follow it,
 * so the sentence SEND or STOP acts on always sits in the bar right next to that button.
 */
sealed interface ActiveCallStage {
    /** Signing a reply: the draft sits above SEND. */
    data object Signing : ActiveCallStage

    /** The sentence being spoken sits above STOP. */
    data class Speaking(val text: String) : ActiveCallStage

    data class ConnectionLost(val notice: String, val isReconnecting: Boolean) : ActiveCallStage

    data class Ended(val reason: ActiveCallViewModel.EndReason) : ActiveCallStage

    companion object {
        fun of(model: ActiveCallViewModel): ActiveCallStage = when (val phase = model.phase) {
            is ActiveCallViewModel.Phase.Ended -> Ended(phase.reason)
            is ActiveCallViewModel.Phase.Interrupted -> ConnectionLost(phase.notice, isReconnecting = true)
            is ActiveCallViewModel.Phase.Disconnected -> ConnectionLost(phase.reason, isReconnecting = false)
            is ActiveCallViewModel.Phase.Connecting, ActiveCallViewModel.Phase.Live ->
                (model.delivery as? ActiveCallViewModel.Delivery.Speaking)?.let { Speaking(it.text) } ?: Signing
        }
    }
}
