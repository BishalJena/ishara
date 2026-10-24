import AVFoundation
import SwiftUI
import UIKit

/// The live front camera: aspect-filled and mirrored, so it moves like a mirror for the
/// user, while the frames recognition reads stay unmirrored. Hosts the camera's single
/// preview layer; it never starts or stops the camera (recognition does).
struct CameraPreviewView: UIViewRepresentable {
    let camera: LiveCamera

    func makeUIView(context: Context) -> PreviewHostView {
        let view = PreviewHostView()
        view.host(camera.previewLayer)
        return view
    }

    func updateUIView(_ view: PreviewHostView, context: Context) {
        view.host(camera.previewLayer)
    }

    static func dismantleUIView(_ view: PreviewHostView, coordinator: ()) {
        view.release()
    }

    /// Portrait and mirrored. The connection only exists once the camera is configured,
    /// so this runs again when the session starts.
    static func configure(_ layer: AVCaptureVideoPreviewLayer) {
        guard let connection = layer.connection else { return }
        if connection.isVideoRotationAngleSupported(90) {
            connection.videoRotationAngle = 90
        }
        if connection.isVideoMirroringSupported {
            connection.automaticallyAdjustsVideoMirroring = false
            connection.isVideoMirrored = true
        }
    }
}

/// Holds the preview layer while its screen is on. When the next screen takes the layer,
/// this view leaves it alone.
final class PreviewHostView: UIView {
    private var previewLayer: AVCaptureVideoPreviewLayer?

    func host(_ preview: AVCaptureVideoPreviewLayer) {
        if previewLayer !== preview {
            NotificationCenter.default.removeObserver(self)
            previewLayer = preview
            NotificationCenter.default.addObserver(
                self, selector: #selector(sessionDidStart),
                name: AVCaptureSession.didStartRunningNotification, object: preview.session)
        }
        if preview.superlayer !== layer {
            layer.addSublayer(preview)
        }
        CameraPreviewView.configure(preview)
        setNeedsLayout()
    }

    func release() {
        guard let previewLayer, previewLayer.superlayer === layer else { return }
        previewLayer.removeFromSuperlayer()
    }

    override func layoutSubviews() {
        super.layoutSubviews()
        guard let previewLayer, previewLayer.superlayer === layer else { return }
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        previewLayer.frame = bounds
        CATransaction.commit()
    }

    /// Posted on the camera's queue.
    @objc nonisolated private func sessionDidStart(_ notification: Notification) {
        Task { @MainActor [weak self] in
            guard let self, let previewLayer = self.previewLayer else { return }
            CameraPreviewView.configure(previewLayer)
        }
    }
}
