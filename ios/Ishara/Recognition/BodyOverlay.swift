import CoreGraphics
import SignPipeline

/// What the camera preview draws on the user so they can see what recognition sees:
/// tracked shoulders and wrists, and the rest line found by calibration. Points are
/// normalized (0...1) in the upright, **unmirrored** image recognition reads, `y` down;
/// the preview maps them onto its mirrored picture.
struct BodyOverlay: Equatable, Sendable {
    /// Pixel size of the upright image the points belong to.
    var imageSize: CGSize
    /// Only shoulders tracked well enough to count for the body check.
    var shoulders: [CGPoint]
    var wrists: [CGPoint]
    /// Wrists below this line count as resting. nil until calibration has finished.
    var restY: Double?

    init(imageSize: CGSize, shoulders: [CGPoint] = [], wrists: [CGPoint] = [], restY: Double? = nil) {
        self.imageSize = imageSize
        self.shoulders = shoulders
        self.wrists = wrists
        self.restY = restY
    }

    init(frame: LandmarkFrame, restY: Double?) {
        let signals = FrameSignals(frame: frame)
        let shoulders = frame.pose.map { pose in
            [SignCLIPLayout.Pose.leftShoulder, SignCLIPLayout.Pose.rightShoulder]
                .map { pose[$0] }
                .filter { $0.poseConfidence >= LandmarkFrame.minimumTrackedShoulderVisibility }
                .map { CGPoint(x: CGFloat($0.x), y: CGFloat($0.y)) }
        } ?? []
        self.init(
            imageSize: CGSize(width: frame.imageSize.width, height: frame.imageSize.height),
            shoulders: shoulders,
            wrists: [signals.leftWrist, signals.rightWrist].compactMap { point in
                point.map { CGPoint(x: CGFloat($0.x), y: CGFloat($0.y)) }
            },
            restY: restY
        )
    }
}
