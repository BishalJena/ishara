package ai.ishara.demo.ui.steer

import ai.ishara.demo.call.ActiveCallViewModel
import ai.ishara.demo.call.notification.OngoingCall
import ai.ishara.demo.call.notification.OngoingCallController
import ai.ishara.demo.call.notification.OngoingCallState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner

/**
 * The steer call's ongoing notification while its screen shows it (iOS `SteerCallView`'s
 * `CallActivityController` calls and its `.isharaEndCallRequested` handler): started when the
 * call is placed, updated with each line, phase and who is driving, ended once the call is over,
 * and its End call ends the call exactly like the End button.
 */
@Composable
fun OngoingCallEffect(model: ActiveCallViewModel) {
    val context = LocalContext.current.applicationContext
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val controller = remember(model) { OngoingCallController(context) }
    DisposableEffect(model) {
        val end = { model.end() }
        OngoingCall.onEndRequested = end
        controller.start(model.setup.contact.name)
        onDispose {
            if (OngoingCall.onEndRequested === end) OngoingCall.onEndRequested = null
            controller.dismiss()
        }
    }
    LaunchedEffect(model) {
        snapshotFlow {
            model.isCallOver to OngoingCallState.of(
                contactName = model.setup.contact.name,
                phase = model.phase,
                captions = model.captions,
                isSteppingIn = model.isSteppingIn,
                connectedAt = model.connectedAt,
            )
        }.collect { (isOver, state) ->
            if (isOver) {
                controller.end(present = lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED))
            } else {
                controller.update(state)
            }
        }
    }
}
