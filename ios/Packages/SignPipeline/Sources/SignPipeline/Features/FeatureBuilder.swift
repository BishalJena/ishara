/// Builds SignCLIP pose features for one clip, porting the Mac path in
/// `spikes/recognition/signclip.py` (`extract`):
///
/// 1. **Assemble** (pose-format `process_holistic`): x and y are scaled to pixels
///    (`x * width`, `y * height`); z is kept as MediaPipe reports it. Pose
///    confidence is the landmark visibility; a detected face or hand point has
///    confidence 1. A missing part becomes zeros with confidence 0.
/// 2. **Select** (`preprocess_pose` → `get_components`): pose 33, the 128 face
///    contour points, left hand 21, right hand 21 (`SignCLIPLayout`).
/// 3. **Mask** (`NumPyPoseBody`): every point whose confidence is exactly 0 is masked.
/// 4. **Normalize** (`Pose.normalize` with right/left shoulder): over the frames
///    where both shoulders are unmasked, `center` is the mean shoulder midpoint
///    (x, y and z) and `scale` is 1 / mean shoulder distance (3D). Both are
///    **clip-level** statistics, so a frame's vector depends on the whole clip.
///    Unmasked points become `(p - center) * scale`; masked points keep their raw
///    assembled values (numpy masked arithmetic leaves masked data untouched).
/// 5. **Hide legs** (`pose_hide_legs`): pose points 25–32 are set to 0.
/// 6. **Flatten** (`nan_to_num`, reshape, `.float()`): x, y, z per point → 609 Float32.
///
/// Like `signclip.py`, a clip without any frame whose shoulders both have
/// visibility ≥ 0.5 is rejected rather than normalized.
public enum FeatureBuilder {
    public static func features(for frames: [LandmarkFrame]) throws -> [[Float]] {
        guard frames.contains(where: \.hasTrackedShoulders) else {
            throw FeatureBuilderError.noTrackedShoulders
        }
        let clip = frames.map(assemble)
        let normalization = try ShoulderNormalization(clip: clip)
        return clip.map { points in
            var vector = [Float]()
            vector.reserveCapacity(SignCLIPLayout.valuesPerFrame)
            for (index, point) in points.enumerated() {
                let value = SignCLIPLayout.Pose.legs.contains(index)
                    ? .zero
                    : point.isMasked ? point.position : normalization.apply(point.position)
                vector.append(Float(value.x))
                vector.append(Float(value.y))
                vector.append(Float(value.z))
            }
            return vector
        }
    }

    private static func assemble(_ frame: LandmarkFrame) -> [AssembledPoint] {
        let width = Double(frame.imageSize.width)
        let height = Double(frame.imageSize.height)

        func points(_ landmarks: [Landmark]?, count: Int, confidence: (Landmark) -> Float)
            -> [AssembledPoint]
        {
            guard let landmarks else {
                return Array(repeating: AssembledPoint(position: .zero, isMasked: true), count: count)
            }
            return landmarks.map { landmark in
                AssembledPoint(
                    position: SIMD3(Double(landmark.x) * width, Double(landmark.y) * height,
                                    Double(landmark.z)),
                    isMasked: confidence(landmark) == 0
                )
            }
        }

        let detected: (Landmark) -> Float = { _ in 1 }
        let face = frame.face.map { mesh in SignCLIPLayout.faceContourIndices.map { mesh[$0] } }
        return points(frame.pose, count: LandmarkFrame.poseCount, confidence: \.poseConfidence)
            + points(face, count: SignCLIPLayout.faceContourIndices.count, confidence: detected)
            + points(frame.leftHand, count: LandmarkFrame.handCount, confidence: detected)
            + points(frame.rightHand, count: LandmarkFrame.handCount, confidence: detected)
    }
}

public enum FeatureBuilderError: Error, Equatable {
    /// No frame has both shoulders at visibility ≥ 0.5.
    case noTrackedShoulders
    /// The shoulders coincide on average, so there is no scale to normalize by.
    case degenerateShoulders
}

struct AssembledPoint {
    var position: SIMD3<Double>
    var isMasked: Bool
}

struct ShoulderNormalization {
    let center: SIMD3<Double>
    let scale: Double

    init(clip: [[AssembledPoint]]) throws {
        let pairs = clip.compactMap { points -> (SIMD3<Double>, SIMD3<Double>)? in
            let right = points[SignCLIPLayout.Pose.rightShoulder]
            let left = points[SignCLIPLayout.Pose.leftShoulder]
            guard !right.isMasked, !left.isMasked else { return nil }
            return (right.position, left.position)
        }
        let count = Double(pairs.count)
        let center = pairs.reduce(SIMD3<Double>.zero) { $0 + ($1.0 + $1.1) / 2 } / count
        let distance = pairs.reduce(0.0) { sum, pair in
            let delta = pair.0 - pair.1
            return sum + (delta * delta).sum().squareRoot()
        } / count
        guard distance > 0, distance.isFinite, center.x.isFinite else {
            throw FeatureBuilderError.degenerateShoulders
        }
        self.center = center
        self.scale = 1 / distance
    }

    func apply(_ position: SIMD3<Double>) -> SIMD3<Double> {
        (position - center) * scale
    }
}
