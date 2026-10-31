package ai.ishara.demo

import ai.ishara.demo.core.CoreEvents
import ai.ishara.demo.core.IsharaCore
import android.app.Application

class IsharaApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        IsharaCore.installMainQueuePump()
        CoreEvents.install()
    }
}
