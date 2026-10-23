import CallSession
import Foundation

/// Run switches, read from launch arguments, for example `-IsharaReplay hello,doctor`,
/// `-IsharaFakeNotDelivered YES` or `-IsharaFixture signing` (Debug builds only).
struct DemoLaunchOptions {
    /// Results the scripted recognizer plays once signing starts, e.g. "hello,doctor,?".
    var replayScript: [RecognitionResult] = []
    /// Make the fake call report the first reply of turn 2 as not delivered.
    var fakeNotDelivered = false
    /// Speed up (below 1) or slow down the fake call's timers.
    var fakeTimeScale = 1.0
    /// Open straight on a prepared screen state for screenshots.
    var fixture: DemoFixture?

    static func from(_ defaults: UserDefaults = .standard) -> DemoLaunchOptions {
        var options = DemoLaunchOptions()
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

    /// "hello, doctor, ?" → sign, sign, unsure. Unknown words are dropped.
    static func parseReplay(_ text: String) -> [RecognitionResult] {
        text.split(separator: ",").compactMap { item in
            let word = item.trimmingCharacters(in: .whitespaces).lowercased()
            if word == ScriptedRecognitionController.unsureOption { return .unsure }
            return Sign(rawValue: word).map(RecognitionResult.sign)
        }
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
}
