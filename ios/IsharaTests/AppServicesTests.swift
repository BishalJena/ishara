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
}
