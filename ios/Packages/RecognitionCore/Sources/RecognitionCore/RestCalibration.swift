public enum CalibrationError: String, Error, Sendable, Equatable {
    /// The recording covers less than `calibrationS`.
    case tooShort = "too_short"
    /// The shoulders were missing from too many frames.
    case cantSee = "cant_see"
}

extension SignDetector {
    /// Finds the rest line from the "hands on the table" recording on the Get ready
    /// screen: a little above the median wrist height, kept within sane limits.
    /// Returns `defaultRestY` when no wrist was seen at all.
    public static func calibrate(
        frames: [DetectorFrame],
        params: DetectorParams = DetectorParams()
    ) throws(CalibrationError) -> Double {
        guard let first = frames.first, let last = frames.last,
              last.t - first.t >= params.calibrationS
        else { throw .tooShort }

        let bodyFrames = frames.count { $0.body }
        if Double(bodyFrames) / Double(frames.count) < params.minBodyFraction {
            throw .cantSee
        }

        let wristHeights = frames.flatMap { $0.wrists.map(\.y) }
        guard let median = median(of: wristHeights) else { return params.defaultRestY }
        return min(max(median - params.restMargin, params.restYMin), params.restYMax)
    }
}

private func median(of values: [Double]) -> Double? {
    guard !values.isEmpty else { return nil }
    let sorted = values.sorted()
    let middle = sorted.count / 2
    return sorted.count.isMultiple(of: 2) ? (sorted[middle - 1] + sorted[middle]) / 2 : sorted[middle]
}
