package ai.ishara.demo.app

import ai.ishara.demo.call.AndroidLineSpeaker
import ai.ishara.demo.call.CallDriver
import ai.ishara.demo.call.FakeCallDriver
import ai.ishara.demo.call.LineSpeaker
import ai.ishara.demo.call.LiveCallDriver
import ai.ishara.demo.call.TestModeVoice
import ai.ishara.demo.models.CallHistory
import ai.ishara.demo.models.UserSettings
import ai.ishara.demo.recognition.RecognitionController
import ai.ishara.demo.recognition.ScriptedRecognitionController
import android.content.Context
import android.os.Build

/** Builds the camera recognizer (MediaPipe + the ASL Signs model) for a run. */
fun interface RecognitionPipelineFactory {
    fun create(options: DemoLaunchOptions, runsInEmulator: Boolean): RecognitionController
}

/** Reads nothing; the default where no phone voice is wanted (JVM tests). */
private object SilentSpeaker : LineSpeaker {
    override fun speak(text: String) = Unit

    override fun stop() = Unit

    override fun shutdown() = Unit
}

/**
 * Picks the call driver and recognizer for this run from the launch options and the backend
 * configuration, and holds what lives as long as the app screen: Recent calls and Settings.
 */
class AppServices(
    val options: DemoLaunchOptions,
    val config: Result<AppConfig>,
    /** Recent calls; in memory unless [current] picks the launch option's place. */
    val history: CallHistory = CallHistory(folder = null),
    val settings: UserSettings = UserSettings(UserSettings.InMemory()),
    /** The emulator has no camera, so the pipeline replays saved videos there. */
    val runsInEmulator: Boolean = false,
    /** The camera pipeline, once it is built into the app; scripted recognition stands in until then. */
    private val pipelineFactory: RecognitionPipelineFactory? = null,
    private val liveDriver: (AppConfig) -> CallDriver = { LiveCallDriver.live(it) },
    /** The phone's voice for test mode; asked for only when a fake call runs. */
    private val testModeSpeaker: () -> LineSpeaker = { SilentSpeaker },
) {
    /** Why a live call can't be placed; null when it can (or when the fake call is in use). */
    val setupProblem: String?
        get() {
            if (options.driver != DemoLaunchOptions.Driver.LIVE) return null
            return config.exceptionOrNull()?.message
        }

    /** One line on Home and Get ready saying which call CALL and Start place. */
    val modeDescription: String
        get() = when (options.driver) {
            DemoLaunchOptions.Driver.FAKE -> "Test mode: a scripted call on this phone. Nothing is dialled."
            DemoLaunchOptions.Driver.LIVE -> ""
        }

    fun makeRecognition(): RecognitionController {
        val pipeline = pipelineFactory
        if (options.recognition == DemoLaunchOptions.Recognition.PIPELINE && pipeline != null) {
            return pipeline.create(options, runsInEmulator)
        }
        return ScriptedRecognitionController(
            script = options.replayScript,
            // Without the camera pipeline a live call is signed from the replay menu.
            offersReplay = options.driver == DemoLaunchOptions.Driver.LIVE &&
                (runsInEmulator || pipeline == null),
            timeScale = options.fakeTimeScale,
        )
    }

    fun makeDriver(recognition: RecognitionController): CallDriver {
        val config = config.getOrNull()
        if (options.driver == DemoLaunchOptions.Driver.LIVE && config != null) return liveDriver(config)
        // The fake call plays its script through the scripted recognizer, if that's in use.
        return FakeCallDriver(
            options = options.fakeDriverOptions,
            recognition = if (options.replayScript.isEmpty()) recognition as? ScriptedRecognitionController else null,
        )
    }

    /**
     * Reads the scripted call aloud in test mode, where no phone line carries the voice. A real
     * call is never voiced on the phone: the receptionist hears it on the line and the user reads
     * the captions. [captionsShown] are already on screen and not read again.
     */
    fun makeTestModeVoice(driver: CallDriver, captionsShown: Int): TestModeVoice? =
        if (driver is FakeCallDriver) TestModeVoice(testModeSpeaker(), captionsShown) else null

    companion object {
        fun current(context: Context, options: DemoLaunchOptions, pipelineFactory: RecognitionPipelineFactory? = null): AppServices {
            val history = when (val location = options.callHistory) {
                DemoLaunchOptions.CallHistoryLocation.FilesDir -> CallHistory.inFilesDir(context.filesDir)
                DemoLaunchOptions.CallHistoryLocation.Memory -> CallHistory(folder = null)
                is DemoLaunchOptions.CallHistoryLocation.Folder -> CallHistory(location.folder)
            }
            val preferences = context.getSharedPreferences(UserSettings.PREFERENCES_FILE, Context.MODE_PRIVATE)
            val settings = UserSettings(UserSettings.Preferences(preferences)).apply { presetNameIfEmpty(options.uiTestName) }
            return AppServices(
                options = options,
                config = AppConfig.fromBuildConfig(),
                history = history,
                settings = settings,
                runsInEmulator = isEmulator,
                pipelineFactory = pipelineFactory,
                testModeSpeaker = { AndroidLineSpeaker(context) },
            )
        }

        val isEmulator: Boolean
            get() = Build.HARDWARE == "ranchu" || Build.HARDWARE == "goldfish" || Build.FINGERPRINT.contains("generic")
    }
}
