import CallSession
import Foundation
import Observation

/// Picks the call driver and recognizer for this run from the launch options and the
/// backend configuration.
@MainActor
struct AppServices {
    let options: DemoLaunchOptions
    let config: Result<AppConfig, AppConfig.Problem>
    /// The simulator has no camera, so the pipeline replays saved videos there.
    var runsInSimulator = AppServices.isSimulator
    /// Recent calls; in memory unless `current(options:)` picks the launch option's place.
    var history = CallHistory(folder: nil)

    static func current(options: DemoLaunchOptions) -> AppServices {
        let config: Result<AppConfig, AppConfig.Problem>
        do {
            config = .success(try AppConfig.loadFromMainBundle())
        } catch {
            config = .failure(error)
        }
        var services = AppServices(options: options, config: config)
        services.history = switch options.callHistory {
        case .applicationSupport: .inApplicationSupport()
        case .memory: CallHistory(folder: nil)
        case .folder(let folder): CallHistory(folder: folder)
        }
        return services
    }

    /// Why a live call can't be placed; nil when it can (or when the fake call is in use).
    var setupProblem: String? {
        guard options.driver == .live, case .failure(let problem) = config else { return nil }
        return problem.message
    }

    /// One line on Home and Get ready saying which call CALL and Start place.
    var modeDescription: String {
        switch options.driver {
        case .fake: "Test mode: a scripted call on this phone. Nothing is dialled."
        case .live: ""
        }
    }

    func makeRecognition() -> any RecognitionController {
        switch options.recognition {
        case .scripted:
            return ScriptedRecognitionController(
                script: options.replayScript,
                offersReplay: options.driver == .live && runsInSimulator,
                timeScale: options.fakeTimeScale)
        case .pipeline:
            let assets = RecognitionAssets.inMainBundle()
            let clips = options.sampleSigns.map(RecognitionAssets.clips(in:)) ?? assets.sampleClips
            let feed: any FrameFeed = runsInSimulator ? ClipFeed(clips: clips) : CameraFeed()
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

    func recoverRecentCalls() async {
        guard options.driver == .live, case .success(let config) = config else { return }
        if let notes = try? await BackendClient(config: config.backend).recentNotes() {
            history.recover(notes)
        }
    }

    func refreshRecentCall(_ record: CallRecord) async {
        guard options.driver == .live, case .success(let config) = config,
              let callID = record.backendCallID ?? record.notes?.callID else { return }
        let client = BackendClient(config: config.backend)
        for attempt in 0...NotesModel.maxRefreshes {
            guard !Task.isCancelled else { return }
            guard let notes = try? await client.notes(callID: callID) else { return }
            history.update(record.id, notes: notes)
            if notes.ready && (notes.presentation?.status == "ready" || notes.outcome == "no_answer") { return }
            guard attempt < NotesModel.maxRefreshes else { return }
            do { try await Task.sleep(for: NotesModel.refreshInterval) } catch { return }
        }
    }

    static var isSimulator: Bool {
        #if targetEnvironment(simulator)
        true
        #else
        false
        #endif
    }
}


/// Backend service reachability.
@MainActor @Observable
final class BackendServiceStatus {
    private(set) var message = "Checking backend…"
    private(set) var online = false
    private(set) var checking = false
    private var config: BackendConfig?

    func monitor(_ config: BackendConfig) async {
        self.config = config
        while !Task.isCancelled {
            await check()
            do { try await Task.sleep(for: .seconds(30)) } catch { return }
        }
    }

    func check() async {
        guard let config, !checking else { return }
        checking = true
        defer { checking = false }
        var request = URLRequest(url: config.baseURL.appending(path: "health"))
        request.timeoutInterval = 6
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            online = (response as? HTTPURLResponse)?.statusCode == 200 && json?["status"] as? String == "ok"
            let missing = json?["missing_config"] as? [String] ?? []
            message = online ? (missing.isEmpty ? "Backend online" : "Backend online · setup incomplete") : "Backend unavailable"
        } catch {
            guard !Task.isCancelled else { return }
            online = false; message = "Backend unreachable"
        }
    }
}
