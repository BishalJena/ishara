/// Tuning for rest calibration and sign segmentation. Durations are in seconds,
/// heights in normalized image y. Defaults match the shared detector spec used by
/// the Python implementation.
public struct DetectorParams: Sendable, Equatable {
    public var calibrationS = 2.0
    public var restMargin = 0.08
    public var defaultRestY = 0.80
    public var restYMin = 0.50
    public var restYMax = 0.95
    public var minBodyFraction = 0.8
    public var startHoldS = 0.10
    public var endRestS = 0.40
    public var preRollS = 0.20
    public var minSignS = 0.30
    public var maxSignS = 4.0
    public var lostBodyS = 0.50

    /// "Continuously for at least X" checks accept a run this much shorter than X,
    /// so a run whose frame times sum to X with rounding error still counts.
    /// Length limits and calibration coverage compare exactly, as in the shared spec.
    public static let timeTolerance = 1e-9

    public init() {}
}
