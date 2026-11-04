package ai.ishara.demo.app

import ai.ishara.demo.BuildConfig
import ai.ishara.demo.call.FakeCallDriver
import ai.ishara.demo.core.call.Sign
import ai.ishara.demo.recognition.RecognitionResult
import android.os.Bundle
import java.io.File

/**
 * Run switches, read from the launch intent's extras with the iOS launch argument names, e.g.
 * `adb shell am start -n ai.ishara.demo/.MainActivity --es IsharaDriver fake --es IsharaFlow classic`.
 * Values may be strings, booleans or numbers (`--es`, `--ez`, `--ed`).
 */
data class DemoLaunchOptions(
    val driver: Driver = Driver.FAKE,
    /** `IsharaFlow classic` keeps the earlier Home; the steer flow is the default. */
    val flow: Flow = Flow.STEER,
    /** Defaults to scripted with the fake call and to the pipeline with the live one. */
    val recognitionOverride: Recognition? = null,
    /** Results the scripted recognizer plays once signing starts, e.g. "hello,doctor,?". */
    val replayScript: List<RecognitionResult> = emptyList(),
    /** Make the fake call report the first reply of turn 2 as not delivered. */
    val fakeNotDelivered: Boolean = false,
    /** Make the receptionist talk over the fake call's first reply while it is spoken. */
    val fakeInterrupt: Boolean = false,
    /** Make the fake call lose its backend connection mid-call (`reconnects` or `staysDown`). */
    val fakeConnectionDrop: FakeCallDriver.ConnectionDrop? = null,
    /**
     * Make the fake Call for me receptionist ask "when?" before offering a time: a time word
     * (`tomorrow`) signs that answer, `tap` leaves it to a tap; `IsharaFakeOpenQuestionText`
     * changes its wording.
     */
    val fakeOpenQuestion: FakeCallDriver.OpenTimeQuestion? = null,
    /** Seconds after a fake Call for me call ended until its notes carry Bolna's summary. */
    val fakeBolnaSummaryDelay: Double? = null,
    /** Speed up (below 1) or slow down the Get ready checklist and the fake call. */
    val fakeTimeScale: Double = 1.0,
    /** Open straight on a prepared screen state for screenshots (debug builds only). */
    val fixture: DemoFixture? = null,
    /** A folder of sign videos the recognition pipeline replays instead of the bundled ones. */
    val sampleSigns: File? = null,
    val callHistory: CallHistoryLocation = CallHistoryLocation.FilesDir,
    /** A name preset in Settings when none is saved (`ISHARA_UITEST_NAME` on iOS). */
    val uiTestName: String? = null,
) {
    enum class Driver(val wire: String) {
        /** The scripted demo call on timers. No backend, nothing is dialled. */
        FAKE("fake"),

        /** The real backend from `local.properties`. Places a real (paid) call. */
        LIVE("live"),
    }

    /** Where Recent calls are kept. */
    sealed interface CallHistoryLocation {
        /** `files/CallHistory` on this phone. */
        data object FilesDir : CallHistoryLocation

        /** This launch only: UI tests start with no calls from earlier runs. */
        data object Memory : CallHistoryLocation

        /** A folder on the device, so a test can relaunch onto the same calls. */
        data class Folder(val folder: File) : CallHistoryLocation
    }

    enum class Recognition(val wire: String) {
        /** Replays fixed results (the fake call's script, `IsharaReplay`, or the replay menu). */
        SCRIPTED("scripted"),

        /** MediaPipe + the ASL Signs model on the camera (or on saved videos). */
        PIPELINE("pipeline"),
    }

    enum class Flow(val wire: String) {
        /** Home is the steer composer: type the request, Ishara runs the call, step in any time. */
        STEER("steer"),

        /** The earlier Home with CALL (sign each reply) and CALL FOR ME (D9). */
        CLASSIC("classic"),
    }

    val recognition: Recognition get() = recognitionOverride ?: if (driver == Driver.LIVE) Recognition.PIPELINE else Recognition.SCRIPTED

    val fakeDriverOptions: FakeCallDriver.Options
        get() = FakeCallDriver.Options(
            timeScale = fakeTimeScale,
            undeliveredStages = if (fakeNotDelivered) setOf(1) else emptySet(),
            interruptedStages = if (fakeInterrupt) setOf(0) else emptySet(),
            connectionDrop = fakeConnectionDrop,
            openTimeQuestion = fakeOpenQuestion,
            bolnaSummaryDelay = fakeBolnaSummaryDelay,
        )

    companion object {
        /** Reads the options from the launch intent's extras. */
        fun from(extras: Bundle?): DemoLaunchOptions = from { key ->
            // Extras may be typed (--ez, --ed) or strings (--es); each is read as its text.
            @Suppress("DEPRECATION")
            extras?.get(key)?.toString()
        }

        /** Live by default: this is a real app. Tests and emulators ask for `IsharaDriver fake`. */
        fun from(value: (String) -> String?): DemoLaunchOptions {
            val openQuestion = value("IsharaFakeOpenQuestion")?.let { answer ->
                FakeCallDriver.OpenTimeQuestion(
                    signedAnswer = Sign.fromWire(answer),
                    question = value("IsharaFakeOpenQuestionText") ?: FakeCallDriver.OpenTimeQuestion().question,
                )
            }
            return DemoLaunchOptions(
                driver = value("IsharaDriver")?.let { raw -> Driver.entries.firstOrNull { it.wire == raw } } ?: Driver.LIVE,
                flow = value("IsharaFlow")?.let { raw -> Flow.entries.firstOrNull { it.wire == raw } } ?: Flow.STEER,
                recognitionOverride = value("IsharaRecognition")?.let { raw -> Recognition.entries.firstOrNull { it.wire == raw } },
                replayScript = parseReplay(value("IsharaReplay").orEmpty()),
                fakeNotDelivered = isTrue(value("IsharaFakeNotDelivered")),
                fakeInterrupt = isTrue(value("IsharaFakeInterrupt")),
                fakeConnectionDrop = value("IsharaFakeConnectionDrop")?.let(FakeCallDriver.ConnectionDrop::fromWire),
                fakeOpenQuestion = openQuestion,
                fakeBolnaSummaryDelay = value("IsharaFakeBolnaSummary")?.toDoubleOrNull()?.takeIf { it > 0 },
                fakeTimeScale = value("IsharaFakeTimeScale")?.toDoubleOrNull()?.takeIf { it > 0 } ?: 1.0,
                fixture = if (BuildConfig.DEBUG) value("IsharaFixture")?.let(DemoFixture::fromWire) else null,
                sampleSigns = value("IsharaSampleSigns")?.let(::File),
                callHistory = when (val raw = value("IsharaCallHistory")) {
                    null -> CallHistoryLocation.FilesDir
                    "memory" -> CallHistoryLocation.Memory
                    else -> CallHistoryLocation.Folder(File(raw))
                },
                uiTestName = value("IsharaUITestName") ?: value("ISHARA_UITEST_NAME"),
            )
        }

        /** "hello, doctor, ?, tomorrow?, frame" → sign, sign, unsure, candidate, hand left the frame. Unknown words are dropped. */
        fun parseReplay(text: String): List<RecognitionResult> =
            text.split(",").mapNotNull(RecognitionResult::fromReplayOption)

        /** Like `UserDefaults.bool`: YES, true or a non-zero number. */
        private fun isTrue(raw: String?): Boolean {
            val value = raw?.trim()?.lowercase() ?: return false
            return value == "yes" || value == "true" || (value.toDoubleOrNull() ?: 0.0) != 0.0
        }
    }
}

/** Prepared screen states for screenshots and quick visual checks. */
enum class DemoFixture(val wire: String) {
    HOME("home"),
    GET_READY("getReady"),
    SIGNING("signing"),
    SPEAKING("speaking"),
    DELIVERED("delivered"),
    NOT_DELIVERED("notDelivered"),
    ENDED("ended"),
    CONNECTION_LOST("connectionLost"),
    COMPOSING("composing"),
    STOPPED("stopped"),
    STOP_TOO_LATE("stopTooLate"),
    DELIVERED_DESPITE_STOP("deliveredDespiteStop"),
    BACKEND_ERROR("backendError"),
    ENDED_NO_CAPTIONS("endedNoCaptions"),
    HANG_UP_UNCONFIRMED("hangUpUnconfirmed"),

    /** The notes of a booked delegated call (D9), with the call service's own summary. */
    NOTES("notes"),
    ;

    companion object {
        fun fromWire(raw: String): DemoFixture? = entries.firstOrNull { it.wire == raw }
    }
}
