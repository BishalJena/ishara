import SwiftUI

/// Screen 3 body, top to bottom in the order the eyes move: camera, chips,
/// draft, quick replies. SEND lives in the action bar below.
struct SigningPanel: View {
    let model: ActiveCallViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            CameraPreviewPlaceholder(state: model.cameraState, message: "Camera (you signing)")
                .overlay(alignment: .bottomTrailing) {
                    ReplayMenu(recognition: model.recognition).padding(10)
                }
            if model.showsDeliveryResult {
                DeliveryBanner(delivery: model.delivery)
            }
            ChipRow(chips: model.chips, onRemove: model.removeChip)
            DraftCard(draft: model.draft)
            QuickReplyBar(onChoose: model.choose)
                .disabled(!model.canUseQuickReplies)
        }
    }
}
