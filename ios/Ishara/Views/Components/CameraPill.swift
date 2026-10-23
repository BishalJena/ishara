import SwiftUI

/// Green = watching, yellow = signing, red = can't see you (WORKFLOW.md).
struct CameraPill: View {
    let state: CameraState

    var body: some View {
        Label {
            Text(title)
        } icon: {
            Image(systemName: "circle.fill")
                .imageScale(.small)
        }
        .font(.subheadline.weight(.semibold))
        .foregroundStyle(foreground)
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(background, in: Capsule())
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Camera: \(title)")
    }

    private var title: String {
        switch state {
        case .watching: "Watching"
        case .signing: "Sign in progress"
        case .cantSee: "Can't see you: move back, hands not visible"
        }
    }

    private var background: Color {
        switch state {
        case .watching: .green
        case .signing: .yellow
        case .cantSee: .red
        }
    }

    private var foreground: Color {
        state == .signing ? .black : .white
    }
}

#Preview {
    VStack {
        CameraPill(state: .watching)
        CameraPill(state: .signing)
        CameraPill(state: .cantSee)
    }
}
