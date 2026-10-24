import AVFoundation
import CoreMedia
import Foundation
import OSLog
import SignPipeline

/// Something the recognition worker processes: a camera or video frame, or a pause in
/// which the last landmarks are held (between replayed clips).
enum FeedItem: Sendable {
    case frame(VideoFrame)
    /// Repeat the last tracked frame for this many seconds, as if the signer held still.
    case hold(seconds: Double)
}

/// Where frames come from: the front camera on a device, saved sign videos in the simulator.
@MainActor
protocol FrameFeed: AnyObject {
    /// The live front camera to preview, when frames come from it; nil for saved videos.
    var camera: LiveCamera? { get }
    var replayOptions: [String] { get }
    /// Called when frames stop for good, for example when camera access is refused.
    var onFailure: ((Error) -> Void)? { get set }
    func items() -> AsyncStream<FeedItem>
    func replay(_ option: String)
    func stop()
}

/// The front camera, continuously. Asks for camera permission (the system prompt) the
/// first time `items()` runs, which is on Get ready. Without permission no frames come
/// and `camera.permission` says why; that is not reported as a failure, because the
/// camera card explains it and offers Settings.
@MainActor
final class CameraFeed: FrameFeed {
    let replayOptions: [String] = []
    var onFailure: ((Error) -> Void)?
    var camera: LiveCamera? { live }
    private let live: LiveCamera
    private let source: CameraFrameSource
    private let access: CameraAccess
    private var pump: Task<Void, Never>?

    init(source: CameraFrameSource = CameraFrameSource(), access: CameraAccess = .system) {
        self.source = source
        self.access = access
        live = LiveCamera(session: source.captureSession, permission: CameraPermission(access.status()))
    }

    func items() -> AsyncStream<FeedItem> {
        let (items, continuation) = AsyncStream<FeedItem>.makeStream(bufferingPolicy: .bufferingNewest(2))
        let source = source
        let access = access
        pump = Task { [weak self] in
            if access.status() == .notDetermined {
                await access.request()
            }
            let permission = CameraPermission(access.status())
            self?.live.permission = permission
            guard permission == .authorized else {
                continuation.finish()
                return
            }
            do {
                for try await frame in source.frames() { continuation.yield(.frame(frame)) }
            } catch {
                if error as? FrameSourceError == .cameraUnavailable {
                    self?.live.isUnavailable = true
                }
                self?.onFailure?(error)
            }
            continuation.finish()
        }
        return items
    }

    func replay(_ option: String) {}

    func stop() {
        pump?.cancel()
        pump = nil
    }
}

/// Saved sign videos played in real time, one at a time, with timestamps shifted so the
/// detector and MediaPipe always see time move forward. Used in the simulator, which has
/// no camera. A clip named `rest` (2–3 s of hands on the table) plays first so Get ready
/// can calibrate; the others are replayed on demand from the call screen.
@MainActor
final class ClipFeed: FrameFeed {
    static let restClipName = "rest"
    /// Held after each clip so the detector sees the hands settle and closes the sign.
    static let holdAfterClip = 0.8

    let clips: [URL]
    /// Saved videos have no live picture to preview.
    let camera: LiveCamera? = nil
    var onFailure: ((Error) -> Void)?
    private var continuation: AsyncStream<FeedItem>.Continuation?
    private var queue: [URL] = []
    private var player: Task<Void, Never>?
    private var nextStart: Double = 0
    init(clips: [URL]) {
        self.clips = clips.sorted { $0.lastPathComponent < $1.lastPathComponent }
    }

    var replayOptions: [String] {
        clips.map(Self.name(of:)).filter { $0 != Self.restClipName }
    }

    func items() -> AsyncStream<FeedItem> {
        continuation?.finish()
        let (items, continuation) = AsyncStream<FeedItem>.makeStream()
        self.continuation = continuation
        if let rest = clips.first(where: { Self.name(of: $0) == Self.restClipName }) {
            enqueue(rest)
        }
        return items
    }

    func replay(_ option: String) {
        guard let clip = clips.first(where: { Self.name(of: $0) == option }) else { return }
        enqueue(clip)
    }

    func stop() {
        player?.cancel()
        player = nil
        queue = []
        continuation?.finish()
        continuation = nil
    }

    private func enqueue(_ clip: URL) {
        queue.append(clip)
        guard player == nil else { return }
        player = Task { [weak self] in await self?.playQueue() }
    }

    private func playQueue() async {
        while !queue.isEmpty, !Task.isCancelled {
            let clip = queue.removeFirst()
            await play(clip)
        }
        player = nil
    }

    private func play(_ clip: URL) async {
        let offset = nextStart
        var last = offset
        do {
            for try await frame in VideoFileFrameSource(url: clip, pacing: .realTime).frames() {
                let t = offset + frame.timestamp.seconds
                last = t
                continuation?.yield(.frame(VideoFrame(
                    pixelBuffer: frame.pixelBuffer,
                    timestamp: CMTime(seconds: t, preferredTimescale: 600),
                    orientation: frame.orientation
                )))
            }
        } catch {
            recognitionLog.error("replay of \(clip.lastPathComponent, privacy: .public) failed: \(String(describing: error), privacy: .public)")
        }
        continuation?.yield(.hold(seconds: Self.holdAfterClip))
        nextStart = last + Self.holdAfterClip + 1.0 / 30
    }

    static func name(of clip: URL) -> String {
        clip.deletingPathExtension().lastPathComponent
    }
}
