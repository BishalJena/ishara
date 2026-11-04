package ai.ishara.demo.call

import ai.ishara.demo.core.call.Brief
import ai.ishara.demo.core.call.BriefRequest
import ai.ishara.demo.core.call.CallNotes
import ai.ishara.demo.core.call.CallSocketClose
import ai.ishara.demo.core.call.CallStore
import ai.ishara.demo.models.CallSetup

/**
 * Places a call and hands back the [CallStore] that holds its state and enforces the SEND
 * safety rules. Everything after that (chips, SEND, STOP, End and backend events) goes
 * through the store, so the real backend and the fake demo call share one set of rules.
 * Use it from the main thread.
 */
interface CallDriver {
    /** Asks for the call (`POST /calls` on the real backend). Throws when it can't be placed. */
    suspend fun start(setup: CallSetup): CallStore

    /** Lets go of the connection once the call screen goes away. Sends nothing. */
    fun close()

    /** D9: the brief the user reads and approves before a delegated call (`POST /briefs`). */
    suspend fun createBrief(request: BriefRequest): Brief

    /** D9: notes of the last call this driver placed (`GET /calls/{id}/notes`). Still works after [close]. */
    suspend fun notes(): CallNotes

    /** Runs when the driver stops bringing a dropped call connection back. */
    var onReconnectStopped: ((ReconnectStop) -> Unit)?
}

sealed class CallDriverError(message: String) : Exception(message) {
    /** Notes were asked for before any call was placed. */
    data object NoCall : CallDriverError("No call has been placed yet.")
}

/** Why a driver stopped reconnecting a dropped call socket. */
sealed interface ReconnectStop {
    /** The backend closed the socket with a code a reconnect can't fix (4401 / 4404 / 4409). */
    data class Refused(val close: CallSocketClose) : ReconnectStop

    /** Every scheduled reconnect was tried. */
    data object AttemptsUsedUp : ReconnectStop
}
