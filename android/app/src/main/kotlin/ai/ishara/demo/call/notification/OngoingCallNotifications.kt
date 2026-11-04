package ai.ishara.demo.call.notification

import ai.ishara.demo.R
import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import kotlin.time.Duration.Companion.seconds

/**
 * Builds and posts the ongoing-call notification, the Android counterpart of the iOS Live
 * Activity (`IsharaWidgets`): the contact, "Ishara is on the call" with a running timer, the
 * latest line, who is answering, and End call. Tapping it opens the app to step in.
 */
object OngoingCallNotifications {
    const val CHANNEL_ID = "ongoing-call"
    const val ONGOING_ID = 1
    const val ENDED_ID = 2
    const val END_CALL_ACTION = "ai.ishara.endCallRequested"
    const val END_CALL_TITLE = "End call"

    /** iOS dismisses the ended Live Activity after a minute. */
    private val ENDED_TIMEOUT = 60.seconds

    private const val PURPLE = 0xFFAF52DE.toInt()

    fun ensureChannel(context: Context) {
        val channel = NotificationChannel(CHANNEL_ID, "Ongoing call", NotificationManager.IMPORTANCE_LOW).apply {
            description = "Shows a call Ishara is handling for you, with End call."
            setShowBadge(false)
        }
        context.getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    fun ongoing(context: Context, state: OngoingCallState): Notification {
        val builder = base(context, state)
            .setOngoing(true)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .addAction(R.drawable.ic_call_end, END_CALL_TITLE, endCallIntent(context))
        // The lock screen shows that a call is on and End, not what was said on it.
        builder.setVisibility(NotificationCompat.VISIBILITY_PRIVATE)
            .setPublicVersion(
                NotificationCompat.Builder(context, CHANNEL_ID)
                    .setSmallIcon(R.drawable.ic_stat_call)
                    .setColor(PURPLE)
                    .setContentTitle(state.headline)
                    .setContentText("Unlock to step in")
                    .applyTimer(state)
                    .addAction(R.drawable.ic_call_end, END_CALL_TITLE, endCallIntent(context))
                    .build(),
            )
        return builder.build()
    }

    /** "Call ended · open Ishara for the gist", for a call that ended while the app was away. */
    fun ended(context: Context, state: OngoingCallState): Notification =
        base(context, state)
            .setContentText(OngoingCallState.ENDED_OUTCOME)
            .setStyle(NotificationCompat.BigTextStyle().bigText(OngoingCallState.ENDED_OUTCOME))
            .setAutoCancel(true)
            .setTimeoutAfter(ENDED_TIMEOUT.inWholeMilliseconds)
            .build()

    fun postEnded(context: Context, state: OngoingCallState) {
        notify(context, ENDED_ID, ended(context, state))
    }

    fun postOngoing(context: Context, state: OngoingCallState) {
        notify(context, ONGOING_ID, ongoing(context, state))
    }

    fun cancelOngoing(context: Context) {
        NotificationManagerCompat.from(context).cancel(ONGOING_ID)
    }

    fun cancelEnded(context: Context) {
        NotificationManagerCompat.from(context).cancel(ENDED_ID)
    }

    private fun notify(context: Context, id: Int, notification: Notification) {
        // Without the permission (Android 13+, refused) nothing is shown; the call goes on as usual.
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED &&
            android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.TIRAMISU
        ) {
            return
        }
        ensureChannel(context)
        NotificationManagerCompat.from(context).notify(id, notification)
    }

    private fun base(context: Context, state: OngoingCallState): NotificationCompat.Builder =
        NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_stat_call)
            .setColor(PURPLE)
            .setCategory(NotificationCompat.CATEGORY_CALL)
            .setOnlyAlertOnce(true)
            .setSilent(true)
            .setContentTitle(state.contactName)
            .setSubText(if (state.isEnded) state.headline else state.status)
            .setContentText(state.quotedLine)
            .setStyle(NotificationCompat.BigTextStyle().bigText(state.quotedLine))
            .setContentIntent(openAppIntent(context))
            .applyTimer(state)

    private fun NotificationCompat.Builder.applyTimer(state: OngoingCallState): NotificationCompat.Builder {
        val start = state.timerStart ?: return setShowWhen(false)
        return setWhen((start * 1000).toLong()).setShowWhen(true).setUsesChronometer(true)
    }

    /** Brings the app's task to the front as the launcher would, never a second copy of the call screen. */
    private fun openAppIntent(context: Context): PendingIntent {
        val intent = Intent(Intent.ACTION_MAIN)
            .addCategory(Intent.CATEGORY_LAUNCHER)
            .setPackage(context.packageName)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED)
        return PendingIntent.getActivity(context, 0, intent, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
    }

    /** Like the Live Activity's End intent: runs inside the app, which owns the call, without opening it. */
    private fun endCallIntent(context: Context): PendingIntent {
        val intent = Intent(context, EndCallReceiver::class.java).setAction(END_CALL_ACTION)
        return PendingIntent.getBroadcast(context, 0, intent, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
    }
}
