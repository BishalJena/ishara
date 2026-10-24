import SwiftUI

/// Screen 3 body, top to bottom in the order the eyes move: camera, chips,
/// draft, quick replies. SEND lives in the action bar below.
struct SigningPanel: View {
    let model: ActiveCallViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Kept short so chips, draft and quick replies fit above SEND without scrolling.
            CameraPreviewPlaceholder(state: model.cameraState, message: "Camera (you signing)", minHeight: 130)
            DeliveryBanner(delivery: model.delivery)
            ChipRow(chips: model.chips, onRemove: model.removeChip)
            DraftCard(draft: model.draft)
            QuickReplyBar(onChoose: model.choose)
                .disabled(!model.canUseQuickReplies)
        }
    }
}
