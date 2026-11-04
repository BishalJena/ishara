package ai.ishara.demo.call.notification

import android.app.ForegroundServiceStartNotAllowedException
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat

/**
 * The one steer call the notification belongs to (iOS posts `ai.ishara.endCallRequested`
 * through NotificationCenter; the call screen listens). The call screen sets [onEndRequested]
 * while it shows a call; End call in the notification runs it. Main thread only.
 */
object OngoingCall {
    var onEndRequested: (() -> Unit)? = null

    /** The state the notification shows now; the service posts it when it starts. */
    var state: OngoingCallState? = null
        internal set
}

/**
 * Keeps the notification in step with a steer call (port of iOS `CallActivityController`):
 * [start] when the call is placed, [update] with each line and with who is driving, [end] once
 * it is over. While the call is on, a foreground service keeps the app (and so the call's
 * connection) running when the user leaves it, as the notification promises.
 */
class OngoingCallController(private val context: Context) {
    private var started = false
    private var ended = false

    fun start(contactName: String) {
        if (started) return
        started = true
        OngoingCall.state = OngoingCallState.starting(contactName)
        try {
            ContextCompat.startForegroundService(context, Intent(context, OngoingCallService::class.java))
        } catch (_: IllegalStateException) {
            // Android 12+ refuses a foreground service from the background (the screen opened as
            // the app left). The notification still shows; only the keep-alive is missing.
            OngoingCall.state?.let { OngoingCallNotifications.postOngoing(context, it) }
        }
    }

    fun update(state: OngoingCallState) {
        if (!started || ended || state == OngoingCall.state) return
        OngoingCall.state = state
        OngoingCallNotifications.postOngoing(context, state)
    }

    /**
     * The call is over: the ongoing notification goes. If the user isn't looking at the app
     * ([present] false) "Call ended · open Ishara for the gist" stays for a minute instead.
     */
    fun end(present: Boolean) {
        if (!started || ended) return
        ended = true
        val last = OngoingCall.state
        removeOngoing()
        if (!present && last != null) OngoingCallNotifications.postEnded(context, last.copy(driving = OngoingCallState.Driving.ENDED))
    }

    /** The call screen went away: nothing more to show about this call. */
    fun dismiss() {
        if (!started || ended) return
        ended = true
        removeOngoing()
    }

    private fun removeOngoing() {
        OngoingCall.state = null
        // A service still starting stops itself once it is in the foreground (stopping it before
        // that crashes the app on some Android versions).
        if (OngoingCallService.isForeground) context.stopService(Intent(context, OngoingCallService::class.java))
        OngoingCallNotifications.cancelOngoing(context)
    }
}

/**
 * The foreground service behind the ongoing-call notification. Type `specialUse`: none of the
 * typed uses fits keeping a relay call's control connection open (it is not the device's own
 * phone call, a media session or a data transfer). Stops with the app's task.
 */
class OngoingCallService : Service() {
    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // A service started for the foreground must get there, even for a call already over.
        val state = OngoingCall.state
        OngoingCallNotifications.ensureChannel(this)
        val notification = OngoingCallNotifications.ongoing(this, state ?: OngoingCallState.starting(""))
        try {
            val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE else 0
            ServiceCompat.startForeground(this, OngoingCallNotifications.ONGOING_ID, notification, type)
            isForeground = true
        } catch (e: IllegalStateException) {
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S || e !is ForegroundServiceStartNotAllowedException) throw e
            state?.let { OngoingCallNotifications.postOngoing(this, it) }
            stopSelf()
            return START_NOT_STICKY
        }
        if (OngoingCall.state == null) stopSelf()
        return START_NOT_STICKY
    }

    override fun onTaskRemoved(rootIntent: Intent?) {
        stopSelf()
    }

    override fun onDestroy() {
        isForeground = false
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
        super.onDestroy()
    }

    companion object {
        /** In the foreground now, so it may be stopped from outside. Main thread only. */
        var isForeground = false
            private set
    }
}

/** End call in the notification: ends the call exactly like the call screen's End button. */
class EndCallReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != OngoingCallNotifications.END_CALL_ACTION) return
        val end = OngoingCall.onEndRequested
        if (end != null) {
            end()
        } else {
            // No call screen holds a call (the app was torn down): nothing to end, so clear what's left.
            OngoingCall.state = null
            if (OngoingCallService.isForeground) context.stopService(Intent(context, OngoingCallService::class.java))
            OngoingCallNotifications.cancelOngoing(context)
        }
    }
}
