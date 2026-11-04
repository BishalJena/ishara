package ai.ishara.demo.app

import ai.ishara.demo.call.ActiveCallViewModel
import ai.ishara.demo.call.CallFollowUp
import ai.ishara.demo.core.call.CallMode
import ai.ishara.demo.models.CallSetup
import ai.ishara.demo.models.Delegation
import ai.ishara.demo.models.SetupDraft
import ai.ishara.demo.recognition.RecognitionController
import ai.ishara.demo.recognition.ScriptedRecognitionController
import ai.ishara.demo.ui.classic.BriefModel
import ai.ishara.demo.ui.notes.NotesModel
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

/**
 * Home → Get ready → Active call, following the workflow's screens. "Call for me" (decision
 * D9) goes Home → Get ready → Brief → Active call (delegated) → Notes. The steer flow (the
 * default) goes Setup → Steer call → Gist. Port of iOS `AppRootView`'s routing; the screens
 * only call these actions. Use it from the main thread.
 */
class AppNavigator(
    val services: AppServices,
    private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate),
) {
    sealed interface Route {
        data object Home : Route

        data class GetReady(val recognition: RecognitionController, val delegated: Boolean) : Route

        data class Brief(val model: BriefModel) : Route

        data class ActiveCall(val model: ActiveCallViewModel) : Route

        /** Steer flow: the one call screen (Ishara runs the call, the user steps in). */
        data class SteerCall(val model: ActiveCallViewModel) : Route

        data class Notes(val model: NotesModel) : Route

        /** A call from Recent calls, read-only. */
        data class RecentCall(val recordId: String) : Route

        /** A debug fixture is being prepared. */
        data object Preparing : Route
    }

    /** Why Settings is open: from its button, or because a steer call needs the caller's name first. */
    sealed interface SettingsPrompt {
        data object Settings : SettingsPrompt

        data class NameForCall(val onContinue: () -> Unit) : SettingsPrompt
    }

    var route: Route by mutableStateOf(Route.Home)
        private set

    var setup: CallSetup by mutableStateOf(CallSetup.demo)
        private set

    /** Why the steer call couldn't be set up (creating its brief failed). */
    var steerProblem: String? by mutableStateOf(null)
        private set

    var settingsPrompt: SettingsPrompt? by mutableStateOf(null)
        private set

    /** What's typed on the steer Home, kept across the call so "Back to the request" finds it. */
    val draft = SetupDraft()

    /** The last ended Call for me call's notes, followed by [CallFollowUp] outside any screen. */
    private var notesFollowUp: Pair<String, NotesModel>? = null

    val isSteerFlow: Boolean get() = services.options.flow == DemoLaunchOptions.Flow.STEER

    /** Why a call can't be placed on the steer Home. */
    val homeProblem: String? get() = services.setupProblem ?: steerProblem

    init {
        startOnFixture()
    }

    // Classic Home

    fun call(chosen: CallSetup) {
        setup = chosen
        route = Route.GetReady(services.makeRecognition(), delegated = false)
    }

    fun callForMe(chosen: CallSetup) {
        setup = chosen
        route = Route.GetReady(services.makeRecognition(), delegated = true)
    }

    // Get ready

    fun getReadyTitle(delegated: Boolean): String = if (delegated) "I'm ready, sign my request" else CALL_TITLE

    fun startFromGetReady(recognition: RecognitionController, delegated: Boolean) {
        val driver = services.makeDriver(recognition)
        route = if (delegated) {
            Route.Brief(BriefModel(setup, driver, recognition))
        } else {
            Route.ActiveCall(ActiveCallViewModel(setup, driver, recognition))
        }
    }

    fun backFromGetReady(recognition: RecognitionController) {
        recognition.stop()
        route = Route.Home
    }

    // Brief (D9)

    fun approveBrief(model: BriefModel, approved: CallSetup) {
        route = Route.ActiveCall(ActiveCallViewModel(approved, model.driver, model.recognition))
    }

    fun backFromBrief(model: BriefModel) {
        model.recognition.stop()
        route = Route.Home
    }

    // Active call and steer call

    fun leaveCall(model: ActiveCallViewModel) {
        model.leave()
        route = Route.Home
    }

    /** D9 and steer: the ended call's notes. A call never placed has no follow-up; its notes say why. */
    fun showNotes(model: ActiveCallViewModel) {
        model.leave()
        val notes = followUp(model) ?: NotesModel(model.setup.contact.name, model.driver)
        notes.start()
        route = Route.Notes(notes)
    }

    /** Saved and followed as soon as the call is over, whatever the user does next. Once per call. */
    fun callOver(model: ActiveCallViewModel) {
        followUp(model)
    }

    private fun followUp(call: ActiveCallViewModel): NotesModel? {
        notesFollowUp?.let { (recordId, notes) -> if (recordId == call.recordId) return notes }
        val notes = CallFollowUp.callEnded(call, services.history) ?: return null
        notesFollowUp = call.recordId to notes
        return notes
    }

    // Steer flow

    /**
     * The typed request becomes the brief (the one approval), then the call starts with it.
     * Signing is only set up if the user taps the sign button on the call.
     */
    fun startSteerCall(chosen: CallSetup) {
        steerProblem = null
        val recognition = services.makeRecognition()
        val driver = services.makeDriver(recognition)
        scope.launch {
            try {
                val brief = driver.createBrief(chosen.steerBriefRequest)
                val ready = chosen.copy(delegation = Delegation(brief, attended = false, mode = CallMode.STEER))
                setup = ready
                route = Route.SteerCall(ActiveCallViewModel(ready, driver, recognition))
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                driver.close()
                steerProblem = "Couldn't set up the call: ${e.message}"
                route = Route.Home
            }
        }
    }

    /** The steer Home's CALL: asks for the caller's name first when none is saved. */
    fun callFromSetup() {
        val settings = services.settings
        if (draft.problem(services.setupProblem) != null) return
        if (settings.name.isBlank()) {
            settingsPrompt = SettingsPrompt.NameForCall { callFromSetup() }
            return
        }
        draft.callSetup(settings, services.setupProblem)?.let(::startSteerCall)
    }

    fun gistDone() {
        draft.clear()
        route = Route.Home
    }

    fun callAgain() {
        startSteerCall(setup)
    }

    // Notes, Recent calls, Settings

    fun notesDone() {
        route = Route.Home
    }

    fun openRecentCall(recordId: String) {
        route = Route.RecentCall(recordId)
    }

    fun openSettings() {
        settingsPrompt = SettingsPrompt.Settings
    }

    /** Closes Settings; a call waiting for the caller's name goes ahead if [continueCall]. */
    fun closeSettings(continueCall: Boolean) {
        val prompt = settingsPrompt
        settingsPrompt = null
        if (continueCall && prompt is SettingsPrompt.NameForCall) prompt.onContinue()
    }

    /**
     * System back. False leaves it to the system (closing the app from Home). A call that is
     * still on stays put: only End hangs up, so back never leaves a call running unseen.
     */
    fun back(): Boolean {
        if (settingsPrompt != null) {
            closeSettings(continueCall = false)
            return true
        }
        when (val current = route) {
            Route.Home -> return false
            Route.Preparing -> return true
            is Route.GetReady -> backFromGetReady(current.recognition)
            is Route.Brief -> backFromBrief(current.model)
            is Route.ActiveCall -> if (current.model.isCallOver) leaveCall(current.model)
            is Route.SteerCall -> if (current.model.isCallOver) leaveCall(current.model)
            is Route.Notes -> if (isSteerFlow) gistDone() else notesDone()
            is Route.RecentCall -> route = Route.Home
        }
        return true
    }

    fun close() {
        scope.cancel()
    }

    private fun startOnFixture() {
        val fixture = services.options.fixture ?: return
        when (fixture) {
            DemoFixture.HOME -> Unit
            DemoFixture.GET_READY -> route = Route.GetReady(ScriptedRecognitionController(), delegated = false)
            DemoFixture.NOTES -> fixture.makeNotes()?.let { notes ->
                notes.start()
                route = Route.Notes(notes)
            }
            else -> {
                route = Route.Preparing
                scope.launch { route = fixture.makeActiveCall()?.let(Route::ActiveCall) ?: Route.Home }
            }
        }
    }

    companion object {
        const val CALL_TITLE = "I'm ready, start call"
    }
}
