package ai.ishara.demo

import ai.ishara.demo.app.AppRoot
import ai.ishara.demo.app.AppViewModel
import ai.ishara.demo.call.notification.OngoingCallNotifications
import ai.ishara.demo.ui.theme.IsharaTheme
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.lifecycle.ViewModelProvider

/** The app's one activity. Launch extras pick the run's options (see `app/DemoLaunchOptions.kt`). */
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        val model = ViewModelProvider(this, AppViewModel.Factory(application, intent.extras))[AppViewModel::class.java]
        setContent {
            IsharaTheme {
                AppRoot(model.navigator)
            }
        }
    }

    override fun onResume() {
        super.onResume()
        // "Call ended · open Ishara for the gist" has done its job once the app is open.
        OngoingCallNotifications.cancelEnded(this)
    }
}
