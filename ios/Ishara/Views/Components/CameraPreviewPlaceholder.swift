import SwiftUI

/// Stands in for the live camera until the sign pipeline is wired in. The
/// simulator has no camera, so this is what the demo shows there.
struct CameraPreviewPlaceholder: View {
    let state: CameraState?
    let message: String
    var minHeight: CGFloat = 180

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // The pill sits above the placeholder content so it can't cover it
            // when the text grows.
            if let state {
                CameraPill(state: state)
            }
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
        .padding(10)
        .frame(maxWidth: .infinity, minHeight: minHeight)
        .background(Color(white: 0.2), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .accessibilityElement(children: .combine)
    }
}

#Preview {
    CameraPreviewPlaceholder(state: .signing, message: "Camera (you signing)")
        .padding()
}
