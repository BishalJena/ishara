import SwiftUI

/// Screen 3 body, top to bottom in the order the eyes move: camera, chips. The draft,
/// quick replies and SEND live in the action bar below, so the draft always sits
/// right above SEND. On a delegated call (D9) there are no chips: the camera is there only
/// to answer the agent (attended), and an unattended call shows no camera at all.
struct SigningPanel: View {
    /// Lets the call screen scroll the chips into view.
    static let chipRowID = "signingPanel.chips"

    let model: ActiveCallViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if model.watchesSigns {
                CameraCard(camera: model.recognition.camera, state: model.cameraState)
                    .overlay(alignment: .bottomTrailing) {
                        ReplayMenu(recognition: model.recognition).padding(10)
                    }
                    .accessibilityElement(children: .contain)
                    .accessibilityIdentifier("call.camera")
            }
            if let message = model.errorMessage {
                CallErrorBanner(message: message)
            }
            if model.showsFramingHint {
                FramingHint()
            }
            if let candidate = model.candidate {
                CandidateTile(sign: candidate, onAccept: model.acceptCandidate, onDismiss: model.dismissCandidate)
            }
            if model.isDelegated {
                DelegatedCallNote(attended: model.isAttended)
            } else {
                if model.showsDeliveryResult {
                    DeliveryBanner(delivery: model.delivery)
                }
                ChipRow(chips: model.chips, onRemove: model.removeChip)
                    .id(Self.chipRowID)
            }
        }
    }
}

/// What the user is (and isn't) expected to do while the agent makes the call for them.
struct DelegatedCallNote: View {
    let attended: Bool

    var body: some View {
        Label {
            Text(attended
                 ? "The agent is making the call for you. When a decision is yours it will ask here: sign or tap one of the answers shown."
                 : "The agent is making the call for you. You can put the phone down; the notes will be here when it ends.")
        } icon: {
            Image(systemName: attended ? "person.wave.2" : "phone.connection")
        }
        .font(.subheadline)
        .foregroundStyle(.secondary)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityIdentifier("call.delegatedNote")
    }
}
