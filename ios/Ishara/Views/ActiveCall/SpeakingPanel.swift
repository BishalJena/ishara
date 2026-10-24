import SwiftUI

/// Screen 4 body: the camera keeps watching so the user can sign the next thing. The
/// sentence being spoken sits in the action bar, right above STOP.
struct SpeakingPanel: View {
    let cameraState: CameraState
    let camera: LiveCamera?
    var isStopTooLate = false
    var errorMessage: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            CameraCard(camera: camera, state: cameraState)
            if isStopTooLate {
                StopTooLateBanner()
            }
            if let errorMessage {
                CallErrorBanner(message: errorMessage)
            }
        }
    }
}

/// The exact sentence being spoken.
struct SpeakingCard: View {
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
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.purple.opacity(0.2), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(isStopRequested ? "Stopping" : "Speaking now"): \(text)")
        .accessibilityIdentifier("call.speaking")
    }
}

#Preview {
    VStack {
        SpeakingPanel(cameraState: .watching, camera: nil)
        SpeakingCard(text: "No, sorry, 4 pm doesn't work. Is there anything tomorrow morning?",
                     isStopRequested: false)
    }
    .padding()
}
