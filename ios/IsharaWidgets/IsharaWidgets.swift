import ActivityKit
import AppIntents
import SwiftUI
import WidgetKit

@main
struct IsharaWidgetsBundle: WidgetBundle {
    var body: some Widget {
        CallActivityWidget()
    }
}

/// Ends the call from the lock screen. Runs inside the app, which owns the call.
struct EndCallIntent: LiveActivityIntent {
    static let title: LocalizedStringResource = "End call"
    static let openAppWhenRun = false

    func perform() async throws -> some IntentResult {
        NotificationCenter.default.post(name: .isharaEndCallRequested, object: nil)
        return .result()
    }
}

extension Notification.Name {
    static let isharaEndCallRequested = Notification.Name("ai.ishara.endCallRequested")
}

/// G5: "Ishara is on the call", the latest line, and End. Unlocking opens the app to step in.
struct CallActivityWidget: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: CallActivityAttributes.self) { context in
            LockScreenCard(context: context)
                .activityBackgroundTint(Color.black.opacity(0.75))
                .activitySystemActionForegroundColor(.white)
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    Avatar(initials: context.attributes.contactInitials).padding(.leading, 4)
                }
                DynamicIslandExpandedRegion(.trailing) {
                    Text(statusText(context.state)).font(.caption2.weight(.semibold)).foregroundStyle(.purple)
                }
                DynamicIslandExpandedRegion(.center) {
                    Text(context.attributes.contactName).font(.headline)
                }
                DynamicIslandExpandedRegion(.bottom) {
                    Text("“\(context.state.latestLine)”").font(.subheadline.weight(.semibold)).lineLimit(2)
                }
            } compactLeading: {
                Image(systemName: context.state.driving == .user ? "keyboard" : "sparkles").foregroundStyle(.purple)
            } compactTrailing: {
                if let startedAt = context.state.startedAt, context.state.driving != .ended {
                    Text(startedAt, style: .timer).monospacedDigit().frame(width: 44)
                } else {
                    Text(context.state.driving == .ended ? "Done" : "…").font(.caption2)
                }
            } minimal: {
                Image(systemName: "phone.fill").foregroundStyle(.purple)
            }
        }
    }
}

private func statusText(_ state: CallActivityAttributes.ContentState) -> String {
    switch state.driving {
    case .agent: "Answering for you"
    case .user: "You're replying"
    case .connecting: "Calling…"
    case .ended: state.outcome ?? "Call ended"
    }
}

private struct Avatar: View {
    let initials: String
    var body: some View {
        Circle().fill(.blue).frame(width: 34, height: 34)
            .overlay(Text(initials).font(.caption.weight(.bold)).foregroundStyle(.white))
    }
}

private struct LockScreenCard: View {
    let context: ActivityViewContext<CallActivityAttributes>

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 10) {
                Avatar(initials: context.attributes.contactInitials)
                VStack(alignment: .leading, spacing: 1) {
                    Text(context.attributes.contactName).font(.subheadline.weight(.bold))
                    HStack(spacing: 4) {
                        Text(context.state.driving == .ended ? "Call ended" : "Ishara is on the call")
                        if let startedAt = context.state.startedAt, context.state.driving != .ended {
                            Text("·"); Text(startedAt, style: .timer).monospacedDigit()
                        }
                    }
                    .font(.caption).foregroundStyle(.white.opacity(0.7))
                }
                Spacer()
                Label(statusText(context.state), systemImage: context.state.driving == .user ? "keyboard" : "sparkles")
                    .font(.caption2.weight(.bold))
                    .padding(.vertical, 4).padding(.horizontal, 8)
                    .background(Color.purple.opacity(0.35), in: Capsule())
                    .foregroundStyle(Color(red: 0.8, green: 0.75, blue: 1))
            }
            Text("“\(context.state.latestLine)”")
                .font(.body.weight(.semibold)).lineLimit(3)
            HStack {
                Text(context.state.driving == .ended ? "Open Ishara for the gist" : "Unlock to step in")
                    .font(.caption).foregroundStyle(.white.opacity(0.7))
                Spacer()
                if context.state.driving != .ended {
                    Button(intent: EndCallIntent()) {
                        Label("End", systemImage: "phone.down.fill").font(.caption.weight(.bold))
                    }
                    .buttonStyle(.borderedProminent).tint(.red).buttonBorderShape(.capsule).controlSize(.small)
                }
            }
        }
        .padding(14)
        .foregroundStyle(.white)
    }
}
