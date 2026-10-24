import SwiftUI

/// Stands in for the live camera when there is none to show: in the simulator, when
/// recognition replays fixed results, or without a front camera. `CameraCard` picks it.
struct CameraPreviewPlaceholder: View {
    let state: CameraState?
    let message: String
    var minHeight: CGFloat = 180

    @Environment(\.dynamicTypeSize) private var typeSize

    /// On the call screens (those with a pill) the figure sits beside the message
    /// instead of above it, so the chips and draft fit above the action bar.
    private var isCompact: Bool { state != nil }

    /// At accessibility text sizes the stand-in figure and message would push the
    /// caption, draft or spoken sentence off screen, so only the pill (which carries
    /// the camera state) is kept.
    private var showsPillOnly: Bool { isCompact && typeSize.isAccessibilitySize }

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
        .frame(maxWidth: .infinity, minHeight: isCompact ? nil : minHeight, alignment: .leading)
        .background(Color(white: 0.2), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder
    private var placeholderContent: some View {
        let layout = isCompact
            ? AnyLayout(HStackLayout(spacing: 12))
            : AnyLayout(VStackLayout(spacing: 8))
        layout {
            Image(systemName: "figure.stand")
                .font(.system(size: isCompact ? 32 : 44))
                .accessibilityHidden(true)
            Text(message)
                .font(.callout)
                .multilineTextAlignment(isCompact ? .leading : .center)
        }
        .foregroundStyle(.white.opacity(0.8))
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: isCompact ? .leading : .center)
        .padding(.horizontal, isCompact ? 8 : 0)
    }
}

#Preview {
    VStack {
        CameraPreviewPlaceholder(state: nil, message: CameraPlaceholder.simulator.message)
        CameraPreviewPlaceholder(state: .signing, message: CameraPlaceholder.simulator.message)
    }
    .padding()
}
