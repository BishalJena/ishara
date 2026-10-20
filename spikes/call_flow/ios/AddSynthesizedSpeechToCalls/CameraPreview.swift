// Camera diagnostic only. No sign recognition or video recording.
// Source: https://developer.apple.com/documentation/avfoundation/avcam-building-a-camera-app
import AVFoundation
import SwiftUI

// Only the capture actor configures the session. This immutable bridge attaches
// that session to Apple's preview layer on the main actor, following AVCam.
struct CameraPreviewSource: @unchecked Sendable {
    private let session: AVCaptureSession
    init(session: AVCaptureSession) { self.session = session }
    @MainActor func connect(to view: CameraPreviewView) {
        view.previewLayer.session = session
        view.previewLayer.videoGravity = .resizeAspectFill
    }
}

actor CameraCapture {
    private let session: AVCaptureSession
    nonisolated let previewSource: CameraPreviewSource
    private let queue = DispatchSerialQueue(label: "dev.ishara.camera-diagnostic")
    nonisolated var unownedExecutor: UnownedSerialExecutor { queue.asUnownedSerialExecutor() }

    init() {
        let session = AVCaptureSession()
        self.session = session
        previewSource = CameraPreviewSource(session: session)
    }

    func start() async -> String {
        guard await AVCaptureDevice.requestAccess(for: .video) else {
            return "Camera permission denied. Enable it in Settings to test preview."
        }
        guard !Task.isCancelled else { return "Camera stopped." }
        if session.inputs.isEmpty {
            do {
                guard let camera = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .front) else {
                    return "Front camera unavailable."
                }
                let input = try AVCaptureDeviceInput(device: camera)
                session.beginConfiguration()
                defer { session.commitConfiguration() }
                session.sessionPreset = .medium
                session.usesApplicationAudioSession = false
                session.automaticallyConfiguresApplicationAudioSession = false
                guard session.canAddInput(input) else { return "Camera input unavailable during this call." }
                session.addInput(input)
            } catch {
                return "Camera could not start. Stop the preview and try again."
            }
        }
        if !session.isRunning { session.startRunning() }
        return session.isRunning ? "Preview started. Check that the picture keeps moving during speech." : "Camera is not running."
    }

    func stop() {
        if session.isRunning { session.stopRunning() }
    }
}

final class CameraPreviewView: UIView {
    override class var layerClass: AnyClass { AVCaptureVideoPreviewLayer.self }
    var previewLayer: AVCaptureVideoPreviewLayer { layer as! AVCaptureVideoPreviewLayer }
}

struct CameraPreview: UIViewRepresentable {
    let source: CameraPreviewSource
    func makeUIView(context: Context) -> CameraPreviewView {
        let view = CameraPreviewView()
        source.connect(to: view)
        return view
    }
    func updateUIView(_ uiView: CameraPreviewView, context: Context) {}
}
