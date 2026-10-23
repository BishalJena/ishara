import AVFoundation

/// Decodes a saved clip into BGRA frames with their presentation timestamps.
/// Used to replay recordings in the simulator, which has no camera.
public final class VideoFileFrameSource: FrameSource {
    public enum Pacing: Sendable {
        /// Yield frames as fast as they decode (tests, batch embedding).
        case asFastAsPossible
        /// Yield each frame at its presentation time, like a live camera.
        case realTime
    }

    public let url: URL
    public let pacing: Pacing

    public init(url: URL, pacing: Pacing = .asFastAsPossible) {
        self.url = url
        self.pacing = pacing
    }

    public func frames() -> AsyncThrowingStream<VideoFrame, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    try await self.decode(into: continuation)
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    private func decode(into continuation: AsyncThrowingStream<VideoFrame, Error>.Continuation) async throws {
        let asset = AVURLAsset(url: url)
        guard let track = try await asset.loadTracks(withMediaType: .video).first else {
            throw FrameSourceError.noVideoTrack
        }
        let orientation = try FrameOrientation(preferredTransform: try await track.load(.preferredTransform))
        let reader = try AVAssetReader(asset: asset)
        let output = AVAssetReaderTrackOutput(track: track, outputSettings: [
            kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA,
        ])
        output.alwaysCopiesSampleData = false
        reader.add(output)
        guard reader.startReading() else {
            throw FrameSourceError.readerFailed(reader.error?.localizedDescription ?? "cannot start")
        }
        defer { reader.cancelReading() }

        let clock = ContinuousClock()
        let start = clock.now
        var firstTimestamp: CMTime?
        while let sample = output.copyNextSampleBuffer() {
            try Task.checkCancellation()
            guard let pixelBuffer = CMSampleBufferGetImageBuffer(sample) else { continue }
            let timestamp = CMSampleBufferGetPresentationTimeStamp(sample)
            if pacing == .realTime {
                let first = firstTimestamp ?? timestamp
                firstTimestamp = first
                let offset = (timestamp - first).seconds
                try await clock.sleep(until: start + .milliseconds(Int64(offset * 1000)))
            }
            continuation.yield(VideoFrame(pixelBuffer: pixelBuffer, timestamp: timestamp, orientation: orientation))
        }
        if reader.status == .failed {
            throw FrameSourceError.readerFailed(reader.error?.localizedDescription ?? "unknown")
        }
    }
}
