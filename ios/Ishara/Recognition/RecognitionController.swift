import CallSession
import Foundation

/// One recognition outcome for a finished sign.
enum RecognitionResult: Equatable, Sendable {
    /// The recognizer is confident: a chip.
    case sign(Sign)
    /// D8 grey zone: a vocabulary sign the model is fairly but not fully sure of. Shown as a
    /// "Did you mean …?" tile; it becomes a chip only when the user taps it.
    case candidate(Sign)
    /// Something was signed but nothing matched well enough: a [?] chip, never spoken.
    case unsure
    /// Like `unsure`, and a hand left the picture during the sign, so the user is told to
    /// keep both hands inside the frame.
    case handLeftFrame
}

extension RecognitionResult {
    /// Replay spellings, for `-IsharaReplay` and the simulator's replay menu: a sign name,
    /// `?` (unsure), `name?` (a "did you mean" candidate) or `frame` (a hand left the frame).
    init?(replayOption text: String) {
        let word = text.trimmingCharacters(in: .whitespaces).lowercased()
        switch word {
        case ScriptedRecognitionController.unsureOption: self = .unsure
        case ScriptedRecognitionController.framingOption: self = .handLeftFrame
        default:
            if word.hasSuffix("?"), let sign = Sign(rawValue: String(word.dropLast())) {
                self = .candidate(sign)
            } else if let sign = Sign(rawValue: word) {
                self = .sign(sign)
            } else {
                return nil
            }
        }
    }
}

/// What the call screen hears from recognition while the user signs.
enum RecognitionEvent: Equatable, Sendable {
    case camera(CameraState)
    case result(RecognitionResult)
}

/// The on-device recognizer as the screens see it, so the app can run with the real
/// pipeline (camera or replayed videos) or with a replay of fixed results.
///
/// Get ready: `start()` turns frames on; `getReady` reports the framing checklist and
/// the 2 s hands-at-rest calibration. Active call: `signingEvents()` streams the camera
/// pill and one result per accepted sign. Rejected sign attempts produce nothing.
@MainActor
protocol RecognitionController: AnyObject {
    /// Checklist and calibration progress for the Get ready screen.
    var getReady: GetReadyModel { get }
    /// Why recognition can't run (no camera permission, missing model), if it can't.
    var failure: String? { get }
    /// Something the user should know that doesn't stop recognition, for example that no
    /// recognition bundle is installed so every sign will show [?].
    var notice: String? { get }
    /// The live front camera to preview, when recognition watches it (pipeline on a
    /// device). nil when there is nothing live to show: saved videos or replayed results.
    var camera: LiveCamera? { get }
    /// Simulator only: things the user can replay by hand, since there is no camera.
    var replayOptions: [String] { get }

    func start()
    /// Results and pill changes from now on. Only one stream is live at a time; a new call
    /// finishes the previous one, so a result can never reach an older call screen.
    func signingEvents() -> AsyncStream<RecognitionEvent>
    func replay(_ option: String)
    func stop()
}
