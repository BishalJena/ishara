import CoreVideo
import CoreMedia
import Foundation
import RecognitionCore
import SignPipeline
@testable import Ishara

/// Scripted holistic landmarks: shoulders, face and both hands, with both wrists at `wristY`.
enum Landmarks {
    static let size = ImageSize(width: 720, height: 1280)
    static let restY: Float = 0.9
    static let signingY: Float = 0.5
    /// The rest line calibration gives at `restY`: 0.9 minus the 0.08 margin.
    static let calibratedRestY = 0.82

    static func frame(
        t: Double, wristY: Float = restY, body: Bool = true, hands: Bool = true, rightHand: Bool = true
    ) -> LandmarkFrame {
        var pose = (0..<LandmarkFrame.poseCount).map { _ in Landmark(x: 0.5, y: 0.5, z: 0, visibility: 0.9) }
        pose[SignCLIPLayout.Pose.leftShoulder] = Landmark(x: 0.6, y: 0.4, z: 0, visibility: body ? 0.9 : 0.1)
        pose[SignCLIPLayout.Pose.rightShoulder] = Landmark(x: 0.4, y: 0.4, z: 0, visibility: body ? 0.9 : 0.1)
        let face = (0..<LandmarkFrame.minimumFaceCount).map { i in
            Landmark(x: 0.5 + Float(i % 10) / 1000, y: 0.25, z: 0)
        }
        let hand = { (x: Float) in
            (0..<LandmarkFrame.handCount).map { i in Landmark(x: x, y: wristY - Float(i) / 200, z: 0) }
        }
        return try! LandmarkFrame(
            timestamp: t, imageSize: size, pose: pose, face: face,
            leftHand: hands ? hand(0.6) : nil, rightHand: hands && rightHand ? hand(0.4) : nil)
    }

    /// `seconds` of frames at 30 fps starting at `start`.
    static func run(from start: Double, seconds: Double, wristY: Float = restY, body: Bool = true) -> [LandmarkFrame] {
        let count = Int((seconds * 30).rounded())
        return (0..<count).map { frame(t: start + Double($0) / 30, wristY: wristY, body: body) }
    }

    /// Framing check, 2 s at rest to calibrate, a little rest, then whatever `after` adds.
    static func calibratedStream(then after: (Double) -> [LandmarkFrame]) -> [LandmarkFrame] {
        let setup = run(from: 0, seconds: 2.6)
        return setup + after(setup.last!.timestamp + 1.0 / 30)
    }

    /// One sign: hands up for `seconds`, then 0.6 s back at rest.
    static func sign(from start: Double, seconds: Double = 0.8) -> [LandmarkFrame] {
        run(from: start, seconds: seconds, wristY: signingY) + run(from: start + seconds, seconds: 0.6)
    }

    /// A one-handed sign: the right hand signs for 0.8 s (the left stays down, untracked), then
    /// its hand landmarks vanish for 0.6 s while the pose still puts its wrist at `wristAfter`.
    static func oneHandedSign(wristAfter: (x: Float, y: Float)) -> (Double) -> [LandmarkFrame] {
        { start in
            (0..<42).map { index in
                let signing = index < 24
                var frame = Self.frame(t: start + Double(index) / 30, wristY: signing ? signingY : restY)
                frame.leftHand = nil
                frame.pose?[15] = Landmark(x: 0.7, y: 1.2, z: 0, visibility: 0.1)
                if signing {
                    frame.pose?[16] = Landmark(x: 0.4, y: signingY, z: 0, visibility: 0.9)
                } else {
                    frame.rightHand = nil
                    frame.pose?[16] = Landmark(x: wristAfter.x, y: wristAfter.y, z: 0, visibility: 0.2)
                }
                return frame
            }
        }
    }

    /// Hands up, then the body leaves the frame mid-sign: a lost-tracking rejection.
    static func lostMidSign(from start: Double) -> [LandmarkFrame] {
        run(from: start, seconds: 0.5, wristY: signingY)
            + run(from: start + 0.5, seconds: 0.7, wristY: signingY, body: false)
            + run(from: start + 1.2, seconds: 0.6)
    }
}

/// Returns the same embedding for every clip.
final class FixedEmbeddingModel: EmbeddingModel {
    let values: [Float]
    var shouldFail = false
    private(set) var calls = 0

    init(_ values: [Float]) { self.values = values }

    func embedding(features: Tensor, mask: Tensor) throws -> Tensor {
        calls += 1
        if shouldFail { throw SignEncoderError.zeroEmbedding }
        return try Tensor(shape: [1, values.count], values: values)
    }
}

/// Two enrolled signs, hello along x and doctor along y, with demanding cut-offs.
let testBundle = RecognitionBundle(
    version: 1, encoder: "test", embeddingDim: 4,
    thresholds: .init(similarity: 0.9, margin: 0.1),
    quality: .init(minPoseFraction: 0.6, minHandFraction: 0.2),
    references: [
        .init(id: "hello-1", label: .hello, embedding: [1, 0, 0, 0]),
        .init(id: "doctor-1", label: .doctor, embedding: [0, 1, 0, 0]),
    ])

/// Answers with scripted landmarks by frame timestamp; ignores the pixels.
final class ScriptedLandmarkProvider: LandmarkProvider {
    private let frames: [Int: LandmarkFrame]

    init(_ frames: [LandmarkFrame]) {
        self.frames = Dictionary(uniqueKeysWithValues: frames.map { (Self.key($0.timestamp), $0) })
    }

    func landmarks(for frame: VideoFrame) throws -> LandmarkFrame {
        guard let landmarks = frames[Self.key(frame.timestamp.seconds)] else {
            throw LandmarkFrameError.invalidImageSize(ImageSize(width: 0, height: 0))
        }
        return landmarks
    }

    private static func key(_ t: Double) -> Int { Int((t * 1000).rounded()) }
}

/// Video frames whose timestamps match `landmarks`, for driving the worker.
func videoFrames(for landmarks: [LandmarkFrame]) -> [VideoFrame] {
    var buffer: CVPixelBuffer?
    CVPixelBufferCreate(nil, 4, 4, kCVPixelFormatType_32BGRA, nil, &buffer)
    return landmarks.map {
        VideoFrame(pixelBuffer: buffer!, timestamp: CMTime(seconds: $0.timestamp, preferredTimescale: 600))
    }
}

/// Plays prepared items, then finishes.
@MainActor
final class ScriptedFeed: FrameFeed {
    var camera: LiveCamera?
    var replayOptions: [String] = []
    var onFailure: ((Error) -> Void)?
    private let prepared: [FeedItem]
    private(set) var replayed: [String] = []
    private(set) var stopCount = 0

    init(_ items: [FeedItem]) { prepared = items }

    func items() -> AsyncStream<FeedItem> {
        AsyncStream { continuation in
            prepared.forEach { continuation.yield($0) }
            continuation.finish()
        }
    }

    func replay(_ option: String) { replayed.append(option) }
    func stop() { stopCount += 1 }
}
