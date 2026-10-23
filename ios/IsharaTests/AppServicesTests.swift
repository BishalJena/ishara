import CallSession
import XCTest
@testable import Ishara

@MainActor
final class AppServicesTests: XCTestCase {
    func testReplayScriptParsesSignsAndQuestionMarks() {
        XCTAssertEqual(
            DemoLaunchOptions.parseReplay(" Hello, doctor ,?, banana,thankyou"),
            [.sign(.hello), .sign(.doctor), .unsure, .sign(.thankyou)])
    }

    func testFakeCallPlaysItsScriptThroughTheScriptedRecognizer() {
        let services = AppServices(options: DemoLaunchOptions())

        XCTAssertTrue(services.makeRecognition() is ScriptedRecognitionController)
        XCTAssertTrue(services.makeDriver(recognition: StubRecognition()) is FakeCallDriver)
    }

    func testPipelineRecognitionWhenAsked() {
        var options = DemoLaunchOptions()
        options.recognitionOverride = .pipeline

        XCTAssertTrue(AppServices(options: options).makeRecognition() is PipelineRecognitionController)
    }
}
