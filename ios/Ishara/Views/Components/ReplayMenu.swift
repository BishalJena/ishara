import SwiftUI

/// Simulator only: the simulator has no camera, so this plays a saved sign video (or a
/// fixed result) through recognition. Hidden when the recognizer offers nothing to replay.
struct ReplayMenu: View {
    let recognition: any RecognitionController

    var body: some View {
        if !recognition.replayOptions.isEmpty {
            Menu {
                ForEach(recognition.replayOptions, id: \.self) { option in
                    Button(option) { recognition.replay(option) }
                }
            } label: {
                Label("Replay a sign", systemImage: "play.rectangle.fill")
                    .font(.subheadline.weight(.semibold))
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(.thinMaterial, in: Capsule())
            }
            .accessibilityHint("Plays a saved sign through recognition, since the simulator has no camera")
        }
    }
}
