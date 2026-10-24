import SwiftUI

/// Screen 4 body: the exact sentence being spoken. The camera keeps watching so
/// the user can sign the next thing.
struct SpeakingPanel: View {
    let text: String
    let cameraState: CameraState
    let isStopRequested: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            CameraPreviewPlaceholder(
                state: cameraState,
                message: "Camera keeps watching\n(you can sign the next thing)"
            )
            SpeakingCard(text: text, isStopRequested: isStopRequested)
        }
    }
}

private struct SpeakingCard: View {
    let text: String
    let isStopRequested: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label(isStopRequested ? "Stopping…" : "Speaking now…", systemImage: "waveform")
                .font(.headline)
                .symbolEffect(.variableColor.iterative, isActive: !isStopRequested)
            Text("\u{201C}\(text)\u{201D}")
                .font(.title2.weight(.semibold))
                .fixedSize(horizontal: false, vertical: true)
            ProgressView()
                .progressViewStyle(.linear)
                .tint(.purple)
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.purple.opacity(0.2), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(isStopRequested ? "Stopping" : "Speaking now"): \(text)")
    }
}

#Preview {
    SpeakingPanel(text: "No, sorry, 4 pm doesn't work. Is there anything tomorrow morning?",
                  cameraState: .watching, isStopRequested: false)
        .padding()
}
