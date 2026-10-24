import AVFoundation
import Observation

/// Whether the app may use the camera, as the screens need to tell it apart.
enum CameraPermission: Equatable, Sendable {
    /// Not asked yet; the system prompt comes up on Get ready.
    case notDetermined
    case authorized
    /// The user said no. They can change it in Settings.
    case denied
    /// Blocked by Screen Time or a device policy; the user may not be able to change it.
    case restricted

    init(_ status: AVAuthorizationStatus) {
        switch status {
        case .notDetermined: self = .notDetermined
        case .authorized: self = .authorized
        case .denied: self = .denied
        case .restricted: self = .restricted
        @unknown default: self = .denied
        }
    }
}

/// Reads and asks for camera permission. Injected so tests never show the system prompt.
struct CameraAccess: Sendable {
    var status: @Sendable () -> AVAuthorizationStatus
    /// Shows the system prompt when not asked yet. Returns once the user has answered.
    var request: @Sendable () async -> Void

    static let system = CameraAccess(
        status: { AVCaptureDevice.authorizationStatus(for: .video) },
        request: { _ = await AVCaptureDevice.requestAccess(for: .video) }
    )
}

/// The front camera as the screens see it while recognition watches it: the capture
/// session to preview (the same one recognition reads frames from) and whether it may run.
@MainActor
@Observable
final class LiveCamera {
    /// Shared with `CameraFrameSource`; a preview attaches to it but never starts it.
    @ObservationIgnored let session: AVCaptureSession
    var permission: CameraPermission
    /// The device has no usable front camera.
    var isUnavailable = false

    init(session: AVCaptureSession, permission: CameraPermission = .notDetermined) {
        self.session = session
        self.permission = permission
    }
}
