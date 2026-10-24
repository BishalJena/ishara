import SwiftUI

/// Screen 3 body, top to bottom in the order the eyes move: camera, chips. The draft,
/// quick replies and SEND live in the action bar below, so the draft always sits
/// right above SEND.
struct SigningPanel: View {
    let model: ActiveCallViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            CameraCard(camera: model.recognition.camera, state: model.cameraState)
                .overlay(alignment: .bottomTrailing) {
                    ReplayMenu(recognition: model.recognition).padding(10)
                }
            if let message = model.errorMessage {
                CallErrorBanner(message: message)
            }
            if model.showsDeliveryResult {
                DeliveryBanner(delivery: model.delivery)
            }
            ChipRow(chips: model.chips, onRemove: model.removeChip)
        }
    }
}
