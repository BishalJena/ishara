import AVFoundation

/// Front-camera frames at 30 fps, 1280×720 (the Mac pilot capture settings),
/// rotated upright for portrait and **not** mirrored: MediaPipe rejects mirrored
/// input and the reference recordings are unmirrored.
///
/// The app must obtain camera permission before calling `frames()`. When the
/// consumer falls behind, only the newest frames are kept.
///
/// `@unchecked Sendable`: the session is only configured, started and stopped on
/// `queue`, and the continuation is only touched there.
public final class CameraFrameSource: NSObject, FrameSource, @unchecked Sendable {
    public static let framesPerSecond: Int32 = 30

    private let session = AVCaptureSession()
    private let queue = DispatchQueue(label: "SignPipeline.CameraFrameSource")
    private var continuation: AsyncThrowingStream<VideoFrame, Error>.Continuation?

    public override init() {
        super.init()
    }

    /// The one capture session behind `frames()`, for an `AVCaptureVideoPreviewLayer`
    /// to show what the camera sees without opening the camera a second time. The
    /// preview layer may mirror its own connection; frames stay unmirrored. Attach
    /// a layer only; configuring, starting and stopping stay with this source.
    public var captureSession: AVCaptureSession { session }

    public func frames() -> AsyncThrowingStream<VideoFrame, Error> {
        AsyncThrowingStream(bufferingPolicy: .bufferingNewest(2)) { continuation in
            queue.async {
                do {
                    try self.configureIfNeeded()
                    self.continuation = continuation
                    self.session.startRunning()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in
                self.queue.async {
                    self.session.stopRunning()
                    self.continuation = nil
                }
            }
        }
    }

    private func configureIfNeeded() throws {
        guard session.inputs.isEmpty else { return }
        guard AVCaptureDevice.authorizationStatus(for: .video) == .authorized else {
            throw FrameSourceError.cameraNotAuthorized
        }
        guard let device = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .front) else {
            throw FrameSourceError.cameraUnavailable
        }
        session.beginConfiguration()
        defer { session.commitConfiguration() }

        if session.canSetSessionPreset(.hd1280x720) { session.sessionPreset = .hd1280x720 }
        let input = try AVCaptureDeviceInput(device: device)
        guard session.canAddInput(input) else { throw FrameSourceError.cameraConfigurationFailed("input") }
        session.addInput(input)

        let output = AVCaptureVideoDataOutput()
        output.videoSettings = [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA]
        output.alwaysDiscardsLateVideoFrames = true
        output.setSampleBufferDelegate(self, queue: queue)
        guard session.canAddOutput(output) else { throw FrameSourceError.cameraConfigurationFailed("output") }
        session.addOutput(output)

        try lockFrameRate(of: device)
        if let connection = output.connection(with: .video) {
            if connection.isVideoRotationAngleSupported(90) { connection.videoRotationAngle = 90 }
            if connection.isVideoMirroringSupported {
                connection.automaticallyAdjustsVideoMirroring = false
                connection.isVideoMirrored = false
            }
        }
    }

    private func lockFrameRate(of device: AVCaptureDevice) throws {
        let rate = Double(Self.framesPerSecond)
        guard device.activeFormat.videoSupportedFrameRateRanges.contains(where: {
            $0.minFrameRate <= rate && rate <= $0.maxFrameRate
        }) else {
            throw FrameSourceError.cameraConfigurationFailed("30 fps unsupported by the active format")
        }
        try device.lockForConfiguration()
        defer { device.unlockForConfiguration() }
        let duration = CMTime(value: 1, timescale: Self.framesPerSecond)
        device.activeVideoMinFrameDuration = duration
        device.activeVideoMaxFrameDuration = duration
    }
}

extension CameraFrameSource: AVCaptureVideoDataOutputSampleBufferDelegate {
    public func captureOutput(
        _ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection
    ) {
        guard let pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        continuation?.yield(VideoFrame(
            pixelBuffer: pixelBuffer,
            timestamp: CMSampleBufferGetPresentationTimeStamp(sampleBuffer)
        ))
    }
}
