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

    /// Where Recent calls are kept.
    enum CallHistoryLocation: Equatable {
        /// `Application Support/CallHistory` on this phone.
        case applicationSupport
        /// This launch only: UI tests start with no calls from earlier runs.
        case memory
        /// A folder of the simulator's Mac, so a UI test can relaunch onto the same calls.
        case folder(URL)
    }

    enum Recognition: String {
        /// Replays fixed results (the fake call's script, `-IsharaReplay`, or the replay menu).
        case scripted
        /// MediaPipe + the ASL Signs model (or SignCLIP) on the camera, or on saved videos
        /// in the simulator.
        case pipeline
    }

    enum Flow: String {
        /// Home is the steer composer: type the request, Ishara runs the call, step in any time.
        case steer
        /// The earlier Home with CALL (sign each reply) and CALL FOR ME (D9), kept for the
        /// UI tests and the rehearsed demo.
        case classic
    }

    /// Live in the app (see `from(_:)`); this initial value is for options built directly in tests.
    var driver: Driver = .fake
    /// `-IsharaFlow classic` keeps the earlier Home; the steer flow is the default.
    var flow: Flow = .steer
    /// Defaults to scripted with the fake call and to the pipeline with the live one.
    var recognitionOverride: Recognition?
    /// Results the scripted recognizer plays once signing starts, e.g. "hello,doctor,?".
    var replayScript: [RecognitionResult] = []
    /// Make the fake call report the first reply of turn 2 as not delivered.
    var fakeNotDelivered = false
    /// Make the receptionist talk over the fake call's first reply while it is spoken.
    var fakeInterrupt = false
    /// Make the fake call lose its backend connection mid-call, e.g.
    /// `-IsharaFakeConnectionDrop staysDown`.
    var fakeConnectionDrop: FakeCallDriver.ConnectionDrop?
    /// Make the fake Call for me receptionist ask "when?" before offering a time:
    /// `-IsharaFakeOpenQuestion tomorrow` signs that time word in answer (any `AskChoice`
    /// time word), `-IsharaFakeOpenQuestion tap` leaves the answer to a tap. Its wording
    /// can be changed with `-IsharaFakeOpenQuestionText "what time would you like to come in"`.
    var fakeOpenQuestion: FakeCallDriver.OpenTimeQuestion?
    /// Make Bolna's own summary reach the fake Call for me notes this many seconds after the
    /// call ended, e.g. `-IsharaFakeBolnaSummary 8`.
    var fakeBolnaSummaryDelay: Double?
    /// Speed up (below 1) or slow down the simulated timers: the Get ready
    /// checklist and the fake call.
    var fakeTimeScale = 1.0
    /// Open straight on a prepared screen state for screenshots.
    var fixture: DemoFixture?
    /// Simulator only: replay the sign videos in this folder on the Mac instead of the
    /// bundled `LocalAssets/SampleSigns`, without a rebuild, e.g.
    /// `-IsharaSampleSigns /path/to/clips` (the simulator reads the Mac's files).
    var sampleSigns: URL?
    /// `-IsharaCallHistory memory`, or `-IsharaCallHistory /path/to/folder` (simulator).
    var callHistory: CallHistoryLocation = .applicationSupport

    var recognition: Recognition {
        recognitionOverride ?? (driver == .live ? .pipeline : .scripted)
    }

    static func from(_ defaults: UserDefaults = .standard) -> DemoLaunchOptions {
        var options = DemoLaunchOptions()
        // Live by default: this is a real app. The scripted driver is only for tests and
        // simulators, which ask for it with `-IsharaDriver fake`.
        options.driver = defaults.string(forKey: "IsharaDriver").flatMap(Driver.init(rawValue:)) ?? .live
        options.flow = defaults.string(forKey: "IsharaFlow").flatMap(Flow.init(rawValue:)) ?? .steer
        options.recognitionOverride = defaults.string(forKey: "IsharaRecognition").flatMap(Recognition.init(rawValue:))
        options.replayScript = parseReplay(defaults.string(forKey: "IsharaReplay") ?? "")
        options.fakeNotDelivered = defaults.bool(forKey: "IsharaFakeNotDelivered")
        options.fakeInterrupt = defaults.bool(forKey: "IsharaFakeInterrupt")
        options.fakeConnectionDrop = defaults.string(forKey: "IsharaFakeConnectionDrop")
            .flatMap(FakeCallDriver.ConnectionDrop.init(rawValue:))
        options.fakeOpenQuestion = defaults.string(forKey: "IsharaFakeOpenQuestion").map {
            var question = FakeCallDriver.OpenTimeQuestion(signedAnswer: Sign(rawValue: $0))
            if let text = defaults.string(forKey: "IsharaFakeOpenQuestionText") { question.question = text }
            return question
        }
        let summaryDelay = defaults.double(forKey: "IsharaFakeBolnaSummary")
        if summaryDelay > 0 {
            options.fakeBolnaSummaryDelay = summaryDelay
        }
        options.sampleSigns = defaults.string(forKey: "IsharaSampleSigns").map { URL(fileURLWithPath: $0, isDirectory: true) }
        options.callHistory = switch defaults.string(forKey: "IsharaCallHistory") {
        case nil: .applicationSupport
        case "memory": .memory
        case let path?: .folder(URL(fileURLWithPath: path, isDirectory: true))
        }
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
            undeliveredStages: fakeNotDelivered ? [1] : [],
            interruptedStages: fakeInterrupt ? [0] : [],
            connectionDrop: fakeConnectionDrop,
            openTimeQuestion: fakeOpenQuestion,
            bolnaSummaryDelay: fakeBolnaSummaryDelay
        )
    }
}

/// Prepared screen states for screenshots and quick visual checks.
enum DemoFixture: String, CaseIterable {
    case home, getReady, signing, speaking, delivered, notDelivered, ended, connectionLost
    case composing, stopped, stopTooLate, deliveredDespiteStop, backendError, endedNoCaptions, hangUpUnconfirmed
    /// The notes of a booked delegated call (D9), with the call service's own summary.
    case notes
}
