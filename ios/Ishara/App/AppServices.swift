import Foundation

/// Picks the call driver and recognizer for this run from the launch options.
@MainActor
struct AppServices {
    let options: DemoLaunchOptions

    static func current(options: DemoLaunchOptions) -> AppServices {
        AppServices(options: options)
    }

    /// Why a call can't be placed; nil when it can.
    var setupProblem: String? { nil }

    /// One line on Home saying which call the CALL button places.
    var modeDescription: String {
        "Demo mode: a scripted call on this phone. Nothing is dialled."
    }

    func makeRecognition() -> any RecognitionController {
        ScriptedRecognitionController(script: options.replayScript, timeScale: options.fakeTimeScale)
    }

    func makeDriver(recognition: any RecognitionController) -> any CallDriver {
        // The fake call plays its script through the scripted recognizer.
        FakeCallDriver(
            options: options.fakeDriverOptions,
            recognition: options.replayScript.isEmpty ? recognition as? ScriptedRecognitionController : nil)
    }
}
