import CallSession
import Foundation
import Observation

/// Recognition that replays fixed results instead of watching the camera: for the fake
/// demo call, for UI tests, and for trying the backend in the simulator without models.
///
/// Get ready ticks on timers. Results come from `emit` (the fake call plays its script
/// through it), from `script` (played once when signing starts), or from `replay`, which
/// the simulator's replay menu calls with a sign name or "?".
@MainActor
@Observable
final class ScriptedRecognitionController: RecognitionController {
    nonisolated static let unsureOption = "?"

    let getReady = GetReadyModel()
    let failure: String? = nil
    let notice: String? = nil
    /// Nothing watches the camera here, so there is no live picture to preview.
    let camera: LiveCamera? = nil
    let replayOptions: [String]

    @ObservationIgnored private let script: [RecognitionResult]
    @ObservationIgnored private let timeScale: Double
    @ObservationIgnored private var continuation: AsyncStream<RecognitionEvent>.Continuation?
    @ObservationIgnored private var tasks: [Task<Void, Never>] = []

    /// - Parameters:
    ///   - script: results played in order, about 2 s apart, once signing starts.
    ///   - offersReplay: list every sign and "?" in the simulator's replay menu.
    init(script: [RecognitionResult] = [], offersReplay: Bool = false, timeScale: Double = 1) {
        self.script = script
        self.timeScale = timeScale
        replayOptions = offersReplay ? Sign.allCases.map(\.rawValue) + [Self.unsureOption] : []
    }

    func start() {
        guard tasks.isEmpty else { return }
        let getReady = getReady
        let timeScale = timeScale
        tasks.append(Task { await getReady.runSimulatedChecks(timeScale: timeScale) })
    }

    func signingEvents() -> AsyncStream<RecognitionEvent> {
        continuation?.finish()
        let (events, continuation) = AsyncStream<RecognitionEvent>.makeStream()
        self.continuation = continuation
        if !script.isEmpty {
            let script = script
            tasks.append(Task { [weak self] in
                for result in script {
                    guard await self?.pause(2) == true else { return }
                    self?.sign(result)
                }
            })
        }
        return events
    }

    func replay(_ option: String) {
        if option == Self.unsureOption {
            sign(.unsure)
        } else if let sign = Sign(rawValue: option) {
            self.sign(.sign(sign))
        }
    }

    /// Shows the yellow pill, then the result, then green again.
    func sign(_ result: RecognitionResult) {
        emit(.camera(.signing))
        tasks.append(Task { [weak self] in
            guard await self?.pause(1.2) == true else { return }
            self?.emit(.result(result))
            self?.emit(.camera(.watching))
        })
    }

    func emit(_ event: RecognitionEvent) {
        continuation?.yield(event)
    }

    func stop() {
        tasks.forEach { $0.cancel() }
        tasks.removeAll()
        continuation?.finish()
        continuation = nil
    }

    private func pause(_ seconds: Double) async -> Bool {
        do {
            try await Task.sleep(for: .seconds(seconds * timeScale))
            return true
        } catch {
            return false
        }
    }
}
