import AVFoundation
import CoreVideo

/// Writes a tiny H.264 clip whose frame `i` is a solid grey of level `10 + 20 * i`.
enum TestVideo {
    struct WriteFailed: Error {
        let reason: String
    }

    static func write(
        frames: Int, fps: Int32, width: Int = 64, height: Int = 48,
        transform: CGAffineTransform = .identity
    ) async throws -> URL {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("signpipeline-\(UUID().uuidString).mov")
        let writer = try AVAssetWriter(outputURL: url, fileType: .mov)
        let input = AVAssetWriterInput(mediaType: .video, outputSettings: [
            AVVideoCodecKey: AVVideoCodecType.h264,
            AVVideoWidthKey: width,
            AVVideoHeightKey: height,
        ])
        input.expectsMediaDataInRealTime = false
        input.transform = transform
        let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: input, sourcePixelBufferAttributes: [
            kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA,
            kCVPixelBufferWidthKey as String: width,
            kCVPixelBufferHeightKey as String: height,
        ])
        writer.add(input)
        guard writer.startWriting() else { throw WriteFailed(reason: "\(String(describing: writer.error))") }
        writer.startSession(atSourceTime: .zero)

        for index in 0..<frames {
            while !input.isReadyForMoreMediaData { try await Task.sleep(for: .milliseconds(2)) }
            guard let pool = adaptor.pixelBufferPool else { throw WriteFailed(reason: "no pixel buffer pool") }
            var buffer: CVPixelBuffer?
            CVPixelBufferPoolCreatePixelBuffer(nil, pool, &buffer)
            guard let buffer else { throw WriteFailed(reason: "no pixel buffer") }
            fill(buffer, level: level(ofFrame: index))
            guard adaptor.append(buffer, withPresentationTime: CMTime(value: CMTimeValue(index), timescale: fps)) else {
                throw WriteFailed(reason: "\(String(describing: writer.error))")
            }
        }
        input.markAsFinished()
        await writer.finishWriting()
        guard writer.status == .completed else { throw WriteFailed(reason: "\(String(describing: writer.error))") }
        return url
    }

    static func level(ofFrame index: Int) -> UInt8 {
        UInt8(10 + 20 * index)
    }

    /// Mean of the blue channel, robust to compression noise.
    static func meanLevel(of buffer: CVPixelBuffer) -> Double {
        CVPixelBufferLockBaseAddress(buffer, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(buffer, .readOnly) }
        let base = CVPixelBufferGetBaseAddress(buffer)!.assumingMemoryBound(to: UInt8.self)
        let rowBytes = CVPixelBufferGetBytesPerRow(buffer)
        let width = CVPixelBufferGetWidth(buffer)
        let height = CVPixelBufferGetHeight(buffer)
        var sum = 0
        for row in 0..<height {
            for column in 0..<width { sum += Int(base[row * rowBytes + column * 4]) }
        }
        return Double(sum) / Double(width * height)
    }

    private static func fill(_ buffer: CVPixelBuffer, level: UInt8) {
        CVPixelBufferLockBaseAddress(buffer, [])
        defer { CVPixelBufferUnlockBaseAddress(buffer, []) }
        let base = CVPixelBufferGetBaseAddress(buffer)!
        let rowBytes = CVPixelBufferGetBytesPerRow(buffer)
        memset(base, Int32(level), rowBytes * CVPixelBufferGetHeight(buffer))
        // Keep alpha opaque.
        let bytes = base.assumingMemoryBound(to: UInt8.self)
        for row in 0..<CVPixelBufferGetHeight(buffer) {
            for column in 0..<CVPixelBufferGetWidth(buffer) { bytes[row * rowBytes + column * 4 + 3] = 255 }
        }
    }
}
