import ActivityKit
import CallSession
import Foundation

/// Keeps the lock-screen Live Activity in step with a steer call: starts it when the call is
/// placed, updates it with each line and with who is driving, ends it with the outcome.
@MainActor
final class CallActivityController {
    private var activity: Activity<CallActivityAttributes>?
    private var lastState: CallActivityAttributes.ContentState?

    func start(contactName: String) {
        guard activity == nil, ActivityAuthorizationInfo().areActivitiesEnabled else { return }
        let initials = InitialsAvatar.initials(contactName)
        let attributes = CallActivityAttributes(contactName: contactName, contactInitials: initials)
        let state = CallActivityAttributes.ContentState(
            latestLine: "Calling \(contactName)…", latestSpeakerIsUs: true, driving: .connecting, startedAt: nil)
        activity = try? Activity.request(attributes: attributes, content: .init(state: state, staleDate: nil))
        lastState = state
    }

    func update(from model: ActiveCallViewModel) {
        guard let activity else { return }
        let latest = model.captions.last
        let driving: CallActivityAttributes.ContentState.Driving = switch model.phase {
        case .connecting: .connecting
        case .ended: .ended
        case .live, .interrupted, .disconnected: model.isSteppingIn ? .user : .agent
        }
        let state = CallActivityAttributes.ContentState(
            latestLine: latest?.text ?? (driving == .connecting ? "Calling \(model.setup.contact.name)…" : "Connected"),
            latestSpeakerIsUs: latest?.speaker != .receptionist,
            driving: driving,
            startedAt: model.connectedAt,
            outcome: model.isCallOver ? "Call ended" : nil)
        guard state != lastState else { return }
        lastState = state
        // Activity isn't Sendable; it is only ever touched from the main actor here.
        nonisolated(unsafe) let live = activity
        Task { await live.update(.init(state: state, staleDate: nil)) }
    }

    func end(outcome: String?) {
        guard let activity else { return }
        var state = lastState ?? CallActivityAttributes.ContentState(
            latestLine: "", latestSpeakerIsUs: true, driving: .ended, startedAt: nil)
        state.driving = .ended
        state.outcome = outcome
        self.activity = nil
        nonisolated(unsafe) let live = activity
        Task { await live.end(.init(state: state, staleDate: nil), dismissalPolicy: .after(.now + 60)) }
    }
}
