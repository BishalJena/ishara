import SwiftUI

/// Stands in for the live camera until the sign pipeline is wired in. The
/// simulator has no camera, so this is what the demo shows there.
struct CameraPreviewPlaceholder: View {
    let state: CameraState?
    let message: String
    var minHeight: CGFloat = 180

    @Environment(\.dynamicTypeSize) private var typeSize

    /// At accessibility text sizes the stand-in figure and message would push the
    /// caption, draft or spoken sentence off screen, so only the pill (which carries
    /// the camera state) is kept.
    private var showsPillOnly: Bool { state != nil && typeSize.isAccessibilitySize }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // The pill sits above the placeholder content so it can't cover it
            // when the text grows.
            if let state {
                CameraPill(state: state)
            }
            if !showsPillOnly {
                placeholderContent
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, minHeight: showsPillOnly ? nil : minHeight, alignment: .leading)
        .background(Color(white: 0.2), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .accessibilityElement(children: .combine)
    }

    private var placeholderContent: some View {
        VStack(spacing: 8) {
            Image(systemName: "figure.stand")
                .font(.system(size: 44))
                .accessibilityHidden(true)
            Text(message)
                .font(.callout)
                .multilineTextAlignment(.center)
        }
        .foregroundStyle(.white.opacity(0.8))
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

#Preview {
    CameraPreviewPlaceholder(state: .signing, message: "Camera (you signing)")
        .padding()
}
