import SwiftUI
import UIKit

/// What the camera area shows.
enum CameraCardContent: Equatable {
    /// The live front camera (also while the permission prompt is up).
    case live
    /// The camera is refused (`.denied`) or blocked (`.restricted`).
    case blocked(CameraPermission)
    /// Nothing live to show; the message says why.
    case placeholder(CameraPlaceholder)

    /// A live camera wins whenever recognition watches one; without one (simulator,
    /// replayed results, Debug fixtures) the placeholder stays.
    @MainActor
    static func content(for camera: LiveCamera?, isSimulator: Bool) -> CameraCardContent {
        guard let camera else { return .placeholder(isSimulator ? .simulator : .cameraOff) }
        if camera.isUnavailable { return .placeholder(.noCamera) }
        switch camera.permission {
        case .denied, .restricted: return .blocked(camera.permission)
        case .authorized, .notDetermined: return .live
        }
    }
}

enum CameraPlaceholder: Equatable {
    /// The simulator has no camera.
    case simulator
    /// Recognition replays fixed results, so the camera isn't used.
    case cameraOff
    /// The device has no usable front camera.
    case noCamera

    var message: String {
        switch self {
        case .simulator: "Camera preview appears on your iPhone."
        case .cameraOff: "Camera is off in demo mode."
        case .noCamera: "No front camera found on this iPhone."
        }
    }
}

/// The camera area of Get ready and the call screens: the live preview with the camera
/// pill on top, a camera-permission message, or a placeholder. Get ready passes no pill
/// state and gets the taller card.
struct CameraCard: View {
    let camera: LiveCamera?
    let state: CameraState?

    @AppStorage("camera.showsBodyOverlay") private var showsOverlay = true
    @Environment(\.dynamicTypeSize) private var typeSize

    private var isCallScreen: Bool { state != nil }

    /// Get ready is where the user frames themselves, so its preview is the tallest. The
    /// call screens keep it small (smaller still at accessibility text sizes) so chips
    /// and the draft stay in view.
    private var previewHeight: CGFloat {
        guard isCallScreen else { return 360 }
        return typeSize.isAccessibilitySize ? 120 : 170
    }

    var body: some View {
        switch CameraCardContent.content(for: camera, isSimulator: AppServices.isSimulator) {
        case .live:
            if let camera { live(camera) }
        case .blocked(let permission):
            CameraBlockedView(permission: permission, state: state)
        case .placeholder(let reason):
            CameraPreviewPlaceholder(state: state, message: reason.message, minHeight: 240)
        }
    }

    /// The pill keeps its place at the top left of the card; on the call screens the
    /// preview sits beside it.
    private func live(_ camera: LiveCamera) -> some View {
        HStack(alignment: .top, spacing: 12) {
            if let state {
                VStack(alignment: .leading, spacing: 8) {
                    CameraPill(state: state)
                    if showsOverlay, !typeSize.isAccessibilitySize {
                        Text("Rest your hands below the dashed line between signs.")
                            .font(.footnote)
                            .foregroundStyle(.white.opacity(0.8))
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                Spacer(minLength: 0)
            }
            preview(camera)
                .frame(maxWidth: isCallScreen ? nil : .infinity)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(white: 0.2), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("camera.preview")
    }

    /// Shaped like the camera's portrait frame, so filling it crops nothing: the user sees
    /// the whole picture recognition sees, from face down to hands resting on the table.
    private func preview(_ camera: LiveCamera) -> some View {
        ZStack {
            CameraPreviewView(camera: camera)
                .accessibilityLabel("Camera preview of you")
            if showsOverlay {
                BodyOverlayView(camera: camera)
            }
        }
        .aspectRatio(Self.frameAspect, contentMode: .fit)
        .frame(height: previewHeight)
        .background(Color.black)
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(alignment: .topTrailing) {
            Button {
                showsOverlay.toggle()
            } label: {
                Image(systemName: showsOverlay ? "figure.arms.open" : "eye.slash")
                    .font(.footnote.weight(.semibold))
                    .padding(6)
                    .background(.thinMaterial, in: Circle())
            }
            .padding(6)
            .accessibilityLabel(showsOverlay ? "Hide tracking dots" : "Show tracking dots")
            .accessibilityIdentifier("camera.overlayToggle")
        }
    }

    /// Width / height of the upright front-camera frame (720×1280).
    static let frameAspect: CGFloat = 9.0 / 16.0
}

/// Camera permission is refused or blocked: say so plainly and, when the user can change
/// it, offer Settings. Recognition can't run, so nothing will be recognised or sent.
private struct CameraBlockedView: View {
    let permission: CameraPermission
    let state: CameraState?

    @Environment(\.openURL) private var openURL

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let state {
                CameraPill(state: state)
            }
            Label("Ishara can't see you", systemImage: "video.slash.fill")
                .font(.headline)
            Text(detail)
                .font(.callout)
                .fixedSize(horizontal: false, vertical: true)
            if permission == .denied {
                Button("Open Settings") {
                    if let url = URL(string: UIApplication.openSettingsURLString) { openURL(url) }
                }
                .buttonStyle(.borderedProminent)
                .accessibilityIdentifier("camera.openSettings")
            }
        }
        .foregroundStyle(.white)
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(white: 0.2), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("camera.blocked")
    }

    private var detail: String {
        permission == .restricted
            ? "Camera access is blocked on this iPhone (Screen Time or a device policy), so signs can't be recognised."
            : "Camera access is off for Ishara, so signs can't be recognised. Turn on Camera in Settings."
    }
}

#Preview {
    VStack {
        CameraCard(camera: nil, state: nil)
        CameraCard(camera: nil, state: .watching)
    }
    .padding()
}
