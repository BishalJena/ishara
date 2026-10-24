import SwiftUI

/// Screen 3 body, top to bottom in the order the eyes move: camera, chips,
/// draft. Quick replies and SEND live in the action bar below.
struct SigningPanel: View {
    let model: ActiveCallViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            CameraPreviewPlaceholder(state: model.cameraState, message: "Camera (you signing)")
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
            DraftCard(draft: model.draft)
        }
    }
}
