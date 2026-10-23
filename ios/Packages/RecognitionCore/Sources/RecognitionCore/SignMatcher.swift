public enum MatchResult: Sendable, Equatable {
    /// Close enough to one sign and clearly ahead of the runner-up: show a chip.
    case sign(label: SignLabel, similarity: Double, margin: Double)
    /// Shown as a [?] chip and never spoken.
    case unsure(UnsureReason)

    public enum UnsureReason: String, Sendable, Equatable {
        /// A score, margin or quality value is missing or not finite.
        case invalidEvidence = "invalid evidence"
        /// Tracking too poor, best match too far, or runner-up too close.
        case insufficientEvidence = "insufficient evidence"
        /// The clip embedding and the references come from different encoders.
        case dimensionMismatch = "dimension mismatch"
    }
}

/// Nearest-reference matching against the user's enrolled signs. Mirrors
/// `rank` + `decision` in spikes/recognition/recognition_data.py: best cosine
/// per sign, ranked by similarity then label, accepted only when the clip was
/// tracked well and both the similarity and the margin over the runner-up clear
/// the frozen cut-offs.
public struct SignMatcher: Sendable {
    public let bundle: RecognitionBundle
    /// Unit-length reference embeddings, or `nil` where a reference cannot be normalized.
    private let unitReferences: [(label: SignLabel, vector: [Double]?)]

    public init(_ bundle: RecognitionBundle) {
        self.bundle = bundle
        unitReferences = bundle.references.map { ($0.label, unitVector($0.embedding)) }
    }

    public func match(embedding: [Float], quality: ClipQuality) -> MatchResult {
        guard embedding.count == bundle.embeddingDim,
              bundle.references.allSatisfy({ $0.embedding.count == embedding.count })
        else { return .unsure(.dimensionMismatch) }

        guard let query = unitVector(embedding),
              unitReferences.allSatisfy({ $0.vector != nil })
        else { return .unsure(.invalidEvidence) }

        let ranking = rank(query)
        let margin = ranking.count >= 2 ? ranking[0].similarity - ranking[1].similarity : nil
        let thresholds = bundle.thresholds
        let required = bundle.quality

        var measurements = [margin, quality.poseFraction, quality.handFraction,
                            thresholds.similarity, thresholds.margin,
                            required.minPoseFraction, required.minHandFraction]
        if let top = ranking.first { measurements.append(top.similarity) }
        guard let top = ranking.first, let margin,
              measurements.allSatisfy({ $0?.isFinite == true })
        else { return .unsure(.invalidEvidence) }

        guard quality.poseFraction >= required.minPoseFraction,
              quality.handFraction >= required.minHandFraction,
              top.similarity >= thresholds.similarity,
              margin >= thresholds.margin
        else { return .unsure(.insufficientEvidence) }

        return .sign(label: top.label, similarity: top.similarity, margin: margin)
    }

    /// Best similarity per sign, highest first; ties go to the alphabetically first label.
    private func rank(_ query: [Double]) -> [(label: SignLabel, similarity: Double)] {
        var best: [SignLabel: Double] = [:]
        for reference in unitReferences {
            guard let vector = reference.vector else { continue }
            let similarity = min(max(dot(query, vector), -1), 1)
            if similarity > best[reference.label, default: -.infinity] {
                best[reference.label] = similarity
            }
        }
        return best
            .map { (label: $0.key, similarity: $0.value) }
            .sorted { $0.similarity != $1.similarity ? $0.similarity > $1.similarity : $0.label < $1.label }
    }
}

private func unitVector(_ values: [Float]) -> [Double]? {
    let vector = values.map(Double.init)
    let norm = dot(vector, vector).squareRoot()
    guard vector.allSatisfy(\.isFinite), norm.isFinite, norm > 0 else { return nil }
    return vector.map { $0 / norm }
}

private func dot(_ a: [Double], _ b: [Double]) -> Double {
    zip(a, b).reduce(0) { $0 + $1.0 * $1.1 }
}
