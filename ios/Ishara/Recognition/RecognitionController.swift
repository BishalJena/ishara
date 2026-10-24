import CallSession
import Foundation

/// One recognition outcome for a finished sign.
enum RecognitionResult: Equatable, Sendable {
    /// The sign matched one of the user's recorded examples closely enough.
    case sign(Sign)
    /// Something was signed but nothing matched well enough: a [?] chip, never spoken.
    case unsure
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
