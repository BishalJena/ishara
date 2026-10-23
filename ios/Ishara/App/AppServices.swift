import Foundation

/// Picks the call driver and recognizer for this run from the launch options and the
/// backend configuration.
@MainActor
struct AppServices {
    let options: DemoLaunchOptions
    let config: Result<AppConfig, AppConfig.Problem>

    static func current(options: DemoLaunchOptions) -> AppServices {
        let config: Result<AppConfig, AppConfig.Problem>
        do {
            config = .success(try AppConfig.loadFromMainBundle())
        } catch {
            config = .failure(error)
        }
        return AppServices(options: options, config: config)
    }

    /// Why a live call can't be placed; nil when it can (or when the fake call is in use).
    var setupProblem: String? {
        guard options.driver == .live, case .failure(let problem) = config else { return nil }
        return problem.message
    }

    /// One line on Home saying which call the CALL button places.
    var modeDescription: String {
        switch options.driver {
        case .fake: "Demo mode: a scripted call on this phone. Nothing is dialled."
        case .live: "Live call through the Ishara backend."
        }
    }

    func makeRecognition() -> any RecognitionController {
        switch options.recognition {
        case .scripted:
            return ScriptedRecognitionController(
                script: options.replayScript,
                offersReplay: options.driver == .live && Self.isSimulator,
                timeScale: options.fakeTimeScale)
        case .pipeline:
            let assets = RecognitionAssets.inMainBundle()
            let feed: any FrameFeed = Self.isSimulator ? ClipFeed(clips: assets.sampleClips) : CameraFeed()
            return PipelineRecognitionController(feed: feed, notice: assets.notice) {
                try assets.makeComponents()
            }
        }
    }

    func makeDriver(recognition: any RecognitionController) -> any CallDriver {
        if options.driver == .live, case .success(let config) = config {
            return LiveCallDriver(config: config.backend)
        }
        // The fake call plays its script through the scripted recognizer, if that's in use.
        return FakeCallDriver(
            options: options.fakeDriverOptions,
            recognition: options.replayScript.isEmpty ? recognition as? ScriptedRecognitionController : nil)
    }

    static var isSimulator: Bool {
        #if targetEnvironment(simulator)
        true
        #else
        false
        #endif
    }
}
