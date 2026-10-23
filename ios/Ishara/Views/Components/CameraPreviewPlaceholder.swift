import SwiftUI

/// Stands in for the live camera until the sign pipeline is wired in. The
/// simulator has no camera, so this is what the demo shows there.
struct CameraPreviewPlaceholder: View {
    let state: CameraState?
    let message: String
    var minHeight: CGFloat = 180

    var body: some View {
        ZStack(alignment: .topLeading) {
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(Color(white: 0.2))

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
            .padding()

            if let state {
                CameraPill(state: state)
                    .padding(10)
            }
        }
        .frame(minHeight: minHeight)
        .accessibilityElement(children: .combine)
    }
}

#Preview {
    CameraPreviewPlaceholder(state: .signing, message: "Camera (you signing)")
        .padding()
}
