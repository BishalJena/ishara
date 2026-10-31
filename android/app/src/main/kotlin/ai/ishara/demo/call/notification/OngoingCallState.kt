package ai.ishara.demo.call.notification

import ai.ishara.demo.call.ActiveCallViewModel.Phase
import ai.ishara.demo.core.call.Caption

/**
 * What the ongoing-call notification shows for a steer call: the Android counterpart of the
 * iOS Live Activity's `CallActivityAttributes.ContentState`, worked out from the call the same
 * way `CallActivityController.update(from:)` does.
 */
data class OngoingCallState(
    val contactName: String,
    val latestLine: String,
    /** The latest line was Ishara's or the user's, not the receptionist's. */
    val latestSpeakerIsUs: Boolean,
    val driving: Driving,
    /** When the call connected (epoch seconds), for the chronometer. */
    val startedAt: Double?,
) {
    enum class Driving { CONNECTING, AGENT, USER, ENDED }

    val isEnded: Boolean get() = driving == Driving.ENDED

    /** The Live Activity's status chip. */
    val status: String
        get() = when (driving) {
            Driving.AGENT -> "Answering for you"
            Driving.USER -> "You're replying"
            Driving.CONNECTING -> "Calling…"
            Driving.ENDED -> ENDED_OUTCOME
        }

    /** The line under the contact's name; the timer runs next to it while connected. */
    val headline: String get() = if (isEnded) "Call ended" else "Ishara is on the call"

    val quotedLine: String get() = "\u201C$latestLine\u201D"

    /** The chronometer runs from the moment the call connected until it ends. */
    val timerStart: Double? get() = startedAt.takeUnless { isEnded }

    companion object {
        /** iOS ends the Live Activity with this outcome. */
        const val ENDED_OUTCOME = "Call ended · open Ishara for the gist"

        fun starting(contactName: String) = OngoingCallState(
            contactName = contactName,
            latestLine = "Calling $contactName…",
            latestSpeakerIsUs = true,
            driving = Driving.CONNECTING,
            startedAt = null,
        )

        fun of(
            contactName: String,
            phase: Phase,
            captions: List<Caption>,
            isSteppingIn: Boolean,
            connectedAt: Double?,
        ): OngoingCallState {
            val driving = when (phase) {
                is Phase.Connecting -> Driving.CONNECTING
                is Phase.Ended -> Driving.ENDED
                Phase.Live, is Phase.Interrupted, is Phase.Disconnected -> if (isSteppingIn) Driving.USER else Driving.AGENT
            }
            val latest = captions.lastOrNull()
            return OngoingCallState(
                contactName = contactName,
                latestLine = latest?.text ?: if (driving == Driving.CONNECTING) "Calling $contactName…" else "Connected",
                latestSpeakerIsUs = latest?.speaker != Caption.Speaker.RECEPTIONIST,
                driving = driving,
                startedAt = connectedAt,
            )
        }
    }
}
