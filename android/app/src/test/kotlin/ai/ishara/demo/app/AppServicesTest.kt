package ai.ishara.demo.app

import ai.ishara.demo.BuildConfig
import ai.ishara.demo.call.CallDriver
import ai.ishara.demo.call.DelegatedDemo
import ai.ishara.demo.call.FakeCallDriver
import ai.ishara.demo.core.call.BackendConfig
import ai.ishara.demo.core.call.Brief
import ai.ishara.demo.core.call.CallMode
import ai.ishara.demo.core.call.CallPurpose
import ai.ishara.demo.core.call.Sign
import ai.ishara.demo.core.call.StartCallRequest
import ai.ishara.demo.models.CallSetup
import ai.ishara.demo.models.Delegation
import ai.ishara.demo.recognition.RecognitionResult
import ai.ishara.demo.recognition.ScriptedRecognitionController
import ai.ishara.demo.support.StubDriver
import ai.ishara.demo.support.StubRecognition
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/** Mirrors ios/IsharaTests/AppServicesTests.swift and the launch-argument tests of the other suites. */
class AppServicesTest {
    private fun options(vararg values: Pair<String, String>): DemoLaunchOptions = DemoLaunchOptions.from(mapOf(*values)::get)

    private val config = Result.success(AppConfig(BackendConfig("https://backend.example.test", "test-token")))
    private val liveDriver = StubDriver()

    private fun services(options: DemoLaunchOptions, config: Result<AppConfig> = this.config, pipeline: RecognitionPipelineFactory? = null, emulator: Boolean = false) =
        AppServices(options, config, runsInEmulator = emulator, pipelineFactory = pipeline, liveDriver = { liveDriver })

    @Test
    fun fakeCallWithScriptedRecognitionByDefaultInTests() {
        val options = DemoLaunchOptions()
        assertEquals(DemoLaunchOptions.Driver.FAKE, options.driver)
        assertEquals(DemoLaunchOptions.Recognition.SCRIPTED, options.recognition)
    }

    @Test
    fun theAppIsLiveAndSteerUnlessTheLaunchSaysOtherwise() {
        val none = options()
        assertEquals(DemoLaunchOptions.Driver.LIVE, none.driver)
        assertEquals(DemoLaunchOptions.Flow.STEER, none.flow)
        assertEquals(DemoLaunchOptions.Recognition.PIPELINE, none.recognition)

        val fake = options("IsharaDriver" to "fake", "IsharaFlow" to "classic", "IsharaRecognition" to "scripted")
        assertEquals(DemoLaunchOptions.Driver.FAKE, fake.driver)
        assertEquals(DemoLaunchOptions.Flow.CLASSIC, fake.flow)
        assertEquals(DemoLaunchOptions.Recognition.SCRIPTED, fake.recognition)
    }

    @Test
    fun liveCallUsesThePipelineUnlessOverridden() {
        val live = DemoLaunchOptions(driver = DemoLaunchOptions.Driver.LIVE)
        assertEquals(DemoLaunchOptions.Recognition.PIPELINE, live.recognition)
        assertEquals(DemoLaunchOptions.Recognition.SCRIPTED, live.copy(recognitionOverride = DemoLaunchOptions.Recognition.SCRIPTED).recognition)
    }

    @Test
    fun replayScriptParsesSignsQuestionMarksCandidatesAndTheFramingCase() {
        assertEquals(
            listOf(RecognitionResult.Recognised(Sign.HELLO), RecognitionResult.Recognised(Sign.DOCTOR), RecognitionResult.Unsure, RecognitionResult.Recognised(Sign.THANKYOU)),
            DemoLaunchOptions.parseReplay(" Hello, doctor ,?, banana,thankyou"),
        )
        assertEquals(
            listOf(RecognitionResult.Candidate(Sign.TOMORROW), RecognitionResult.HandLeftFrame, RecognitionResult.Recognised(Sign.YES)),
            DemoLaunchOptions.parseReplay("tomorrow?, frame, banana?, yes"),
        )
        assertEquals(DemoLaunchOptions.parseReplay("yes,?"), options("IsharaReplay" to "yes,?").replayScript)
    }

    @Test
    fun launchSwitchesTurnOnTheFakeCallsEdgeCases() {
        val plain = options().fakeDriverOptions
        assertNull(plain.connectionDrop)
        assertEquals(emptySet<Int>(), plain.interruptedStages)
        assertEquals(emptySet<Int>(), plain.undeliveredStages)
        assertEquals(1.0, plain.timeScale, 0.0)

        val chaos = options(
            "IsharaFakeInterrupt" to "YES",
            "IsharaFakeNotDelivered" to "true",
            "IsharaFakeConnectionDrop" to "staysDown",
            "IsharaFakeTimeScale" to "0.05",
        ).fakeDriverOptions
        assertEquals(setOf(0), chaos.interruptedStages)
        assertEquals(setOf(1), chaos.undeliveredStages)
        assertEquals(FakeCallDriver.ConnectionDrop.STAYS_DOWN, chaos.connectionDrop)
        assertEquals(0.05, chaos.timeScale, 0.0)
        assertEquals(FakeCallDriver.ConnectionDrop.RECONNECTS, options("IsharaFakeConnectionDrop" to "reconnects").fakeDriverOptions.connectionDrop)
        assertEquals(emptySet<Int>(), options("IsharaFakeInterrupt" to "NO").fakeDriverOptions.interruptedStages)
        assertEquals("a non-positive scale is ignored", 1.0, options("IsharaFakeTimeScale" to "0").fakeTimeScale, 0.0)
    }

    @Test
    fun bolnaSummaryLaunchArgument() {
        assertNull(options().fakeDriverOptions.bolnaSummaryDelay)
        assertEquals(8.0, options("IsharaFakeBolnaSummary" to "8").fakeDriverOptions.bolnaSummaryDelay)
        assertNull(options("IsharaFakeBolnaSummary" to "0").fakeDriverOptions.bolnaSummaryDelay)
    }

    @Test
    fun openTimeQuestionLaunchArgument() {
        assertNull(options().fakeDriverOptions.openTimeQuestion)
        assertEquals(Sign.TOMORROW, options("IsharaFakeOpenQuestion" to "tomorrow").fakeDriverOptions.openTimeQuestion?.signedAnswer)
        val tap = options("IsharaFakeOpenQuestion" to "tap").fakeDriverOptions.openTimeQuestion!!
        assertNull(tap.signedAnswer)
        assertEquals(DelegatedDemo.OPEN_QUESTION, tap.question)
        val worded = "what time would will would you like to come in"
        assertEquals(worded, options("IsharaFakeOpenQuestion" to "tap", "IsharaFakeOpenQuestionText" to worded).fakeDriverOptions.openTimeQuestion?.question)
    }

    @Test
    fun callHistoryLaunchArgument() {
        assertEquals(DemoLaunchOptions.CallHistoryLocation.FilesDir, options().callHistory)
        assertEquals(DemoLaunchOptions.CallHistoryLocation.Memory, options("IsharaCallHistory" to "memory").callHistory)
        assertEquals(
            DemoLaunchOptions.CallHistoryLocation.Folder(File("/data/local/tmp/calls")),
            options("IsharaCallHistory" to "/data/local/tmp/calls").callHistory,
        )
    }

    @Test
    fun fixtureNameAndUiTestNameLaunchArguments() {
        assertEquals(if (BuildConfig.DEBUG) DemoFixture.NOT_DELIVERED else null, options("IsharaFixture" to "notDelivered").fixture)
        assertNull(options("IsharaFixture" to "nonsense").fixture)
        assertEquals("Riya", options("IsharaUITestName" to "Riya").uiTestName)
        assertEquals("Riya", options("ISHARA_UITEST_NAME" to "Riya").uiTestName)
        assertEquals(File("/sdcard/clips"), options("IsharaSampleSigns" to "/sdcard/clips").sampleSigns)
    }

    @Test
    fun delegatedSetupStartsADelegatedCallWithItsBrief() {
        assertEquals(StartCallRequest(contactId = "clinic", purpose = CallPurpose.DOCTOR_APPOINTMENT), CallSetup.demo.startRequest)
        val setup = CallSetup.demo.copy(delegation = Delegation(Brief("b9", "…", "book a doctor's appointment", emptyList()), attended = true))
        assertEquals(
            StartCallRequest(contactId = "clinic", purpose = CallPurpose.DOCTOR_APPOINTMENT, mode = CallMode.DELEGATED, briefId = "b9", attended = true),
            setup.startRequest,
        )
    }

    @Test
    fun liveModeWithoutConfigCannotCallAndNeverDials() {
        val services = services(DemoLaunchOptions(driver = DemoLaunchOptions.Driver.LIVE), config = Result.failure(AppConfig.Problem.MissingAppToken))

        assertEquals(AppConfig.Problem.MissingAppToken.message, services.setupProblem)
        assertTrue("without a config nothing can dial", services.makeDriver(StubRecognition()) is FakeCallDriver)
    }

    @Test
    fun liveModeWithConfigUsesTheBackend() {
        val services = services(DemoLaunchOptions(driver = DemoLaunchOptions.Driver.LIVE))

        assertNull(services.setupProblem)
        assertEquals("", services.modeDescription)
        assertSame(liveDriver, services.makeDriver(StubRecognition()))
    }

    @Test
    fun fakeModeNeverUsesTheBackend() {
        val services = services(DemoLaunchOptions(), config = Result.failure(AppConfig.Problem.MissingBackendUrl))

        assertNull(services.setupProblem)
        assertEquals("Test mode: a scripted call on this phone. Nothing is dialled.", services.modeDescription)
        assertTrue(services.makeDriver(StubRecognition()) is FakeCallDriver)
    }

    @Test
    fun pipelineRecognitionWhenAskedAndBuilt() {
        val built = StubRecognition()
        var askedOnEmulator: Boolean? = null
        val pipeline = RecognitionPipelineFactory { _, emulator ->
            askedOnEmulator = emulator
            built
        }
        val services = services(DemoLaunchOptions(recognitionOverride = DemoLaunchOptions.Recognition.PIPELINE), pipeline = pipeline, emulator = true)

        assertSame(built, services.makeRecognition())
        assertEquals(true, askedOnEmulator)
        assertTrue("scripted recognition never asks the pipeline", services(DemoLaunchOptions(), pipeline = pipeline).makeRecognition() is ScriptedRecognitionController)
    }

    @Test
    fun withoutThePipelineALiveCallIsSignedFromTheReplayMenu() {
        val live = services(DemoLaunchOptions(driver = DemoLaunchOptions.Driver.LIVE)).makeRecognition()
        val fake = services(DemoLaunchOptions()).makeRecognition()

        assertTrue(live is ScriptedRecognitionController)
        assertTrue(live.replayOptions.isNotEmpty())
        assertTrue("the fake call plays its own signs", fake.replayOptions.isEmpty())
        assertNull("replayed results never use the camera", live.camera)
    }

    @Test
    fun theFakeCallPlaysItsScriptOnlyWithoutAReplayScript() {
        val scripted = services(DemoLaunchOptions())
        val recognition = scripted.makeRecognition()
        val driver: CallDriver = scripted.makeDriver(recognition)
        assertTrue(driver is FakeCallDriver)
        assertFalse(recognition.replayOptions.isNotEmpty())
    }
}
