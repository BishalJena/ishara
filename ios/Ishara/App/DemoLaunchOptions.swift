import CallSession
import Foundation

/// Run switches, read from launch arguments, for example `-IsharaDriver live`,
/// `-IsharaFakeNotDelivered YES` or `-IsharaFixture signing` (Debug builds only).
struct DemoLaunchOptions {
    enum Driver: String {
        /// The scripted demo call on timers. No backend, nothing is dialled.
        case fake
        /// The real backend from `Config/Secrets.xcconfig`. Places a real (paid) call.
        case live
    }

    enum Recognition: String {
        /// Replays fixed results (the fake call's script, `-IsharaReplay`, or the replay menu).
        case scripted
        /// MediaPipe + the ASL Signs model (or SignCLIP) on the camera, or on saved videos
        /// in the simulator.
        case pipeline
    }

    /// Fake unless asked otherwise, so running the app never places a call by surprise.
    var driver: Driver = .fake
    /// Defaults to scripted with the fake call and to the pipeline with the live one.
    var recognitionOverride: Recognition?
    /// Results the scripted recognizer plays once signing starts, e.g. "hello,doctor,?".
    var replayScript: [RecognitionResult] = []
    /// Make the fake call report the first reply of turn 2 as not delivered.
    var fakeNotDelivered = false
    /// Speed up (below 1) or slow down the simulated timers: the Get ready
    /// checklist and the fake call.
    var fakeTimeScale = 1.0
    /// Open straight on a prepared screen state for screenshots.
    var fixture: DemoFixture?

    var recognition: Recognition {
        recognitionOverride ?? (driver == .live ? .pipeline : .scripted)
    }

    static func from(_ defaults: UserDefaults = .standard) -> DemoLaunchOptions {
        var options = DemoLaunchOptions()
        options.driver = defaults.string(forKey: "IsharaDriver").flatMap(Driver.init(rawValue:)) ?? .fake
        options.recognitionOverride = defaults.string(forKey: "IsharaRecognition").flatMap(Recognition.init(rawValue:))
        options.replayScript = parseReplay(defaults.string(forKey: "IsharaReplay") ?? "")
        options.fakeNotDelivered = defaults.bool(forKey: "IsharaFakeNotDelivered")
        let scale = defaults.double(forKey: "IsharaFakeTimeScale")
        if scale > 0 {
            options.fakeTimeScale = scale
        }
        #if DEBUG
        options.fixture = defaults.string(forKey: "IsharaFixture").flatMap(DemoFixture.init(rawValue:))
        #endif
        return options
    }

    /// "hello, doctor, ?, tomorrow?, frame" → sign, sign, unsure, candidate, hand left the
    /// frame. Unknown words are dropped.
    static func parseReplay(_ text: String) -> [RecognitionResult] {
        text.split(separator: ",").compactMap { RecognitionResult(replayOption: String($0)) }
    }

    var fakeDriverOptions: FakeCallDriver.Options {
        FakeCallDriver.Options(
            timeScale: fakeTimeScale,
            undeliveredStages: fakeNotDelivered ? [1] : []
        )
    }
}

/// Prepared screen states for screenshots and quick visual checks.
enum DemoFixture: String, CaseIterable {
    case home, getReady, signing, speaking, delivered, notDelivered, ended, connectionLost
    case composing, stopped, stopTooLate, deliveredDespiteStop, backendError, endedNoCaptions, hangUpUnconfirmed
}
