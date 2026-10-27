import CallSession
import XCTest
@testable import Ishara

@MainActor
final class AppServicesTests: XCTestCase {
    func testFakeCallWithScriptedRecognitionByDefault() {
        let options = DemoLaunchOptions()
        XCTAssertEqual(options.driver, .fake)
        XCTAssertEqual(options.recognition, .scripted)
    }

    func testLiveCallUsesThePipelineUnlessOverridden() {
        var options = DemoLaunchOptions()
        options.driver = .live
        XCTAssertEqual(options.recognition, .pipeline)
        options.recognitionOverride = .scripted
        XCTAssertEqual(options.recognition, .scripted)
    }

    func testReplayScriptParsesSignsAndQuestionMarks() {
        XCTAssertEqual(
            DemoLaunchOptions.parseReplay(" Hello, doctor ,?, banana,thankyou"),
            [.sign(.hello), .sign(.doctor), .unsure, .sign(.thankyou)])
    }

    func testReplayScriptParsesCandidatesAndTheFramingCase() {
        XCTAssertEqual(
            DemoLaunchOptions.parseReplay("tomorrow?, frame, banana?, yes"),
            [.candidate(.tomorrow), .handLeftFrame, .sign(.yes)])
    }

    func testDelegatedSetupStartsADelegatedCallWithItsBrief() {
        var setup = CallSetup.demo
        XCTAssertEqual(setup.startRequest, StartCallRequest(contactID: "clinic", purpose: .doctorAppointment))
        let brief = Brief(briefID: "b9", text: "…", goal: "book a doctor's appointment", constraints: [])
        setup.delegation = Delegation(brief: brief, attended: true)

        XCTAssertEqual(setup.startRequest, StartCallRequest(
            contactID: "clinic", purpose: .doctorAppointment, mode: .delegated, briefID: "b9", attended: true))
    }

    func testLiveModeWithoutConfigCannotCall() {
        var options = DemoLaunchOptions()
        options.driver = .live
        let services = AppServices(options: options, config: .failure(.missingAppToken))

        XCTAssertEqual(services.setupProblem, AppConfig.Problem.missingAppToken.message)
        XCTAssertTrue(services.makeDriver(recognition: StubRecognition()) is FakeCallDriver,
                      "without a config nothing can dial")
    }

    func testLiveModeWithConfigUsesTheBackend() {
        var options = DemoLaunchOptions()
        options.driver = .live
        let services = AppServices(options: options, config: .success(AppConfig(backend: testBackend)))

        XCTAssertNil(services.setupProblem)
        XCTAssertTrue(services.makeDriver(recognition: StubRecognition()) is LiveCallDriver)
    }

    func testFakeModeNeverUsesTheBackend() {
        let services = AppServices(options: DemoLaunchOptions(), config: .success(AppConfig(backend: testBackend)))

        XCTAssertNil(services.setupProblem)
        XCTAssertTrue(services.makeDriver(recognition: StubRecognition()) is FakeCallDriver)
    }

    func testPipelineRecognitionWhenAsked() {
        var options = DemoLaunchOptions()
        options.recognitionOverride = .pipeline
        let services = AppServices(options: options, config: .failure(.missingBackendURL))

        XCTAssertTrue(services.makeRecognition() is PipelineRecognitionController)
    }

    func testPipelineOnADeviceWatchesTheLiveCamera() {
        var options = DemoLaunchOptions()
        options.recognitionOverride = .pipeline
        var services = AppServices(options: options, config: .failure(.missingBackendURL))
        services.runsInSimulator = false

        XCTAssertNotNil(services.makeRecognition().camera)
    }

    func testSimulatorAndScriptedRecognitionHaveNoLiveCamera() {
        var pipeline = DemoLaunchOptions()
        pipeline.recognitionOverride = .pipeline
        var simulator = AppServices(options: pipeline, config: .failure(.missingBackendURL))
        simulator.runsInSimulator = true
        var scripted = AppServices(options: DemoLaunchOptions(), config: .failure(.missingBackendURL))
        scripted.runsInSimulator = false

        XCTAssertNil(simulator.makeRecognition().camera, "the simulator replays saved videos")
        XCTAssertNil(scripted.makeRecognition().camera, "replayed results never use the camera")
    }
}
