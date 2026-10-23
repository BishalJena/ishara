import Foundation

/// Everything that can happen to an active call, from the backend and from the
/// on-device sign pipeline. Mirrors the backend → app WebSocket messages in PLAN §3.
enum CallEvent: Equatable, Sendable {
    // Backend
    case status(CallStatus)
    case caption(text: String, at: Date)
    case draft(turnID: TurnID, text: String, source: DraftSource)
    case spoken(turnID: TurnID)
    case notDelivered(turnID: TurnID)
    case error(message: String)

    // On-device recognition
    case recognition(RecognitionResult)
    case camera(CameraState)
}

/// The view model's only way to reach the call. `FakeCallDriver` plays the demo
/// script; a later step plugs in the backend WebSocket client and the sign pipeline.
@MainActor
protocol CallDriver: AnyObject {
    /// Events for the current call. Finishes when the call is over.
    var events: AsyncStream<CallEvent> { get }

    /// Ask the backend to place the call (`POST /calls`).
    func start(_ setup: CallSetup)

    /// The recognised chips changed; recompose the draft (`chips {turn_id, chips[]}`).
    /// Unsure chips are never included.
    func updateChips(turnID: TurnID, words: [String])

    /// The user tapped SEND with exactly this text (`approve {turn_id, text}`). Single use.
    func approve(turnID: TurnID, text: String)

    /// Cancel output that has not been spoken yet (`stop`).
    func stop()

    /// End the call (`end`).
    func end()
}
