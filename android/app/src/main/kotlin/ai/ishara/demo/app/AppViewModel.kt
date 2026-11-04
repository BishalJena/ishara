package ai.ishara.demo.app

import android.app.Application
import android.os.Bundle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider

/**
 * Holds the run's services and navigation across configuration changes, made once per
 * activity like iOS's `@State services`: a second set would bring a second call history.
 */
class AppViewModel(application: Application, extras: Bundle?) : ViewModel() {
    val navigator = AppNavigator(AppServices.current(application, DemoLaunchOptions.from(extras)))

    override fun onCleared() {
        navigator.close()
    }

    class Factory(private val application: Application, private val extras: Bundle?) : ViewModelProvider.Factory {
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            @Suppress("UNCHECKED_CAST") // Only AppViewModel is ever asked of this factory.
            return AppViewModel(application, extras) as T
        }
    }
}
