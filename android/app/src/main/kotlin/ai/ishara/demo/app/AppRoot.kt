package ai.ishara.demo.app

import ai.ishara.demo.app.AppNavigator.Route
import ai.ishara.demo.call.ActiveCallViewModel
import ai.ishara.demo.ui.classic.ActiveCallScreen
import ai.ishara.demo.ui.classic.BriefScreen
import ai.ishara.demo.ui.classic.GetReadyScreen
import ai.ishara.demo.ui.components.LocalRunsInEmulator
import ai.ishara.demo.ui.home.HomeScreen
import ai.ishara.demo.ui.home.RecentCallScreen
import ai.ishara.demo.ui.home.SettingsSheet
import ai.ishara.demo.ui.notes.NotesScreen
import ai.ishara.demo.ui.steer.SetupScreen
import ai.ishara.demo.ui.steer.SteerCallScreen
import ai.ishara.demo.ui.steer.SteerGistScreen
import ai.ishara.demo.ui.steer.steerColors
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId
import kotlinx.coroutines.flow.first

/**
 * The app's one screen at a time, switched on [AppNavigator.route]. Effects that belong to a
 * route rather than to how it looks live here: Get ready's checks start, the call and brief
 * models run while shown, and an ended call is saved and followed.
 */
@OptIn(ExperimentalComposeUiApi::class)
@Composable
fun AppRoot(navigator: AppNavigator) {
    val services = navigator.services
    BackHandler(enabled = navigator.route != Route.Home || navigator.settingsPrompt != null) { navigator.back() }
    CompositionLocalProvider(LocalRunsInEmulator provides services.runsInEmulator) {
        Surface(
            // iOS's systemBackground (white / black) behind every screen and the system bars.
            color = steerColors().background,
            // Test tags double as resource ids, so UI Automator and adb dumps see the iOS identifiers.
            modifier = Modifier.fillMaxSize().semantics { testTagsAsResourceId = true },
        ) {
            Box(Modifier.fillMaxSize().safeDrawingPadding()) { RouteContent(navigator) }
        }
        navigator.settingsPrompt?.let { prompt ->
            SettingsSheet(
                settings = services.settings,
                forCall = prompt is AppNavigator.SettingsPrompt.NameForCall,
                onClose = navigator::closeSettings,
            )
        }
    }
}

@Composable
private fun RouteContent(navigator: AppNavigator) {
    val services = navigator.services
    when (val route = navigator.route) {
        Route.Home -> if (navigator.isSteerFlow) {
            SetupScreen(
                draft = navigator.draft,
                settings = services.settings,
                history = services.history,
                modeDescription = services.modeDescription,
                setupProblem = navigator.homeProblem,
                onCall = navigator::callFromSetup,
                onOpenSettings = navigator::openSettings,
                onOpenRecent = navigator::openRecentCall,
            )
        } else {
            HomeScreen(
                setup = navigator.setup,
                modeDescription = services.modeDescription,
                setupProblem = services.setupProblem,
                history = services.history,
                onCall = navigator::call,
                onCallForMe = navigator::callForMe,
                onOpenRecent = navigator::openRecentCall,
            )
        }
        is Route.GetReady -> {
            LaunchedEffect(route.recognition) { route.recognition.start() }
            GetReadyScreen(
                recognition = route.recognition,
                modeDescription = services.modeDescription,
                startTitle = navigator.getReadyTitle(route.delegated),
                onStart = { navigator.startFromGetReady(route.recognition, route.delegated) },
                onBack = { navigator.backFromGetReady(route.recognition) },
            )
        }
        is Route.Brief -> {
            LaunchedEffect(route.model) { route.model.run() }
            BriefScreen(
                model = route.model,
                modeDescription = services.modeDescription,
                onApprove = { approved -> navigator.approveBrief(route.model, approved) },
                onBack = { navigator.backFromBrief(route.model) },
            )
        }
        is Route.ActiveCall -> {
            RunCall(route.model, navigator)
            ActiveCallScreen(
                model = route.model,
                onLeave = { navigator.leaveCall(route.model) },
                onShowNotes = if (route.model.isDelegated) ({ navigator.showNotes(route.model) }) else null,
            )
        }
        is Route.SteerCall -> {
            RunCall(route.model, navigator)
            SteerCallScreen(
                model = route.model,
                onLeave = { navigator.leaveCall(route.model) },
                onShowNotes = { navigator.showNotes(route.model) },
            )
        }
        is Route.Notes -> if (navigator.isSteerFlow) {
            SteerGistScreen(model = route.model, onDone = navigator::gistDone, onCallAgain = navigator::callAgain)
        } else {
            NotesScreen(model = route.model, onDone = navigator::notesDone)
        }
        is Route.RecentCall -> RecentCallScreen(
            onRefresh = services::refreshRecentCall,
            record = services.history.records.firstOrNull { it.id == route.recordId },
            onBack = { navigator.back() },
            onDelete = {
                services.history.delete(route.recordId)
                navigator.back()
            },
        )
        Route.Preparing -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
    }
}

/**
 * Places the call and feeds it recognition while shown; saves and follows it once it is over.
 * In test mode the phone also reads Ishara's lines aloud while the call screen is up.
 */
@Composable
private fun RunCall(model: ActiveCallViewModel, navigator: AppNavigator) {
    LaunchedEffect(model) { model.run() }
    LaunchedEffect(model) {
        snapshotFlow { model.isCallOver }.first { it }
        navigator.callOver(model)
    }
    val voice = remember(model) { navigator.services.makeTestModeVoice(model.driver, captionsShown = model.captions.size) }
    if (voice != null) {
        LaunchedEffect(voice) {
            snapshotFlow { model.captions to model.isCallOver }.collect { (captions, isOver) -> voice.update(captions, isOver) }
        }
        DisposableEffect(voice) { onDispose { voice.close() } }
    }
}
