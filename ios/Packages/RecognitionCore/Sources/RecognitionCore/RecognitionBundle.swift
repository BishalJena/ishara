import Foundation

public enum BundleValidationError: Error, Sendable, Equatable {
    case unsupportedVersion(Int)
    case unknownLabel(String)
    case invalidEmbeddingDimension(Int)
    case nonFiniteThresholds
    case invalidQualityRequirements
    case embeddingDimensionMismatch(referenceID: String, expected: Int, actual: Int)
    case nonFiniteEmbedding(referenceID: String)
    case zeroNormEmbedding(referenceID: String)
    case tooFewLabels(Int)
}

/// The frozen recognition setup exported by the Mac tool: the user's enrolled
/// reference embeddings plus the cut-offs set on the calibration session (R2b).
///
/// Decoding validates the bundle. The memberwise initializer does not, so call
/// `validate()` on bundles built in code.
public struct RecognitionBundle: Codable, Sendable, Equatable {
    public static let supportedVersion = 1

    public struct Thresholds: Codable, Sendable, Equatable {
        public var similarity: Double
        public var margin: Double

        public init(similarity: Double, margin: Double) {
            self.similarity = similarity
            self.margin = margin
        }
    }

    public struct QualityRequirements: Codable, Sendable, Equatable {
        public var minPoseFraction: Double
        public var minHandFraction: Double

        public init(minPoseFraction: Double = 0.6, minHandFraction: Double = 0.2) {
            self.minPoseFraction = minPoseFraction
            self.minHandFraction = minHandFraction
        }

        enum CodingKeys: String, CodingKey {
            case minPoseFraction = "min_pose_fraction"
            case minHandFraction = "min_hand_fraction"
        }
    }

    public struct Reference: Codable, Sendable, Equatable {
        public var id: String
        public var label: SignLabel
        public var embedding: [Float]

        public init(id: String, label: SignLabel, embedding: [Float]) {
            self.id = id
            self.label = label
            self.embedding = embedding
        }

        enum CodingKeys: String, CodingKey {
            case id, label, embedding
        }

        public init(from decoder: any Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            id = try container.decode(String.self, forKey: .id)
            let rawLabel = try container.decode(String.self, forKey: .label)
            guard let label = SignLabel(rawValue: rawLabel) else {
                throw BundleValidationError.unknownLabel(rawLabel)
            }
            self.label = label
            embedding = try container.decode([Float].self, forKey: .embedding)
        }
    }

    public var version: Int
    public var encoder: String
    public var embeddingDim: Int
    public var thresholds: Thresholds
    public var quality: QualityRequirements
    public var references: [Reference]

    public init(
        version: Int = RecognitionBundle.supportedVersion,
        encoder: String,
        embeddingDim: Int,
        thresholds: Thresholds,
        quality: QualityRequirements = QualityRequirements(),
        references: [Reference]
    ) {
        self.version = version
        self.encoder = encoder
        self.embeddingDim = embeddingDim
        self.thresholds = thresholds
        self.quality = quality
        self.references = references
    }

    enum CodingKeys: String, CodingKey {
        case version, encoder, thresholds, quality, references
        case embeddingDim = "embedding_dim"
    }

    public init(from decoder: any Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        version = try container.decode(Int.self, forKey: .version)
        guard version == Self.supportedVersion else {
            throw BundleValidationError.unsupportedVersion(version)
        }
        encoder = try container.decode(String.self, forKey: .encoder)
        embeddingDim = try container.decode(Int.self, forKey: .embeddingDim)
        thresholds = try container.decode(Thresholds.self, forKey: .thresholds)
        quality = try container.decode(QualityRequirements.self, forKey: .quality)
        references = try container.decode([Reference].self, forKey: .references)
        try validate()
    }

    /// Decodes and validates an exported bundle.
    public static func load(from data: Data) throws -> RecognitionBundle {
        try JSONDecoder().decode(RecognitionBundle.self, from: data)
    }

    /// Rejects bundles the matcher could not use safely: a wrong format version,
    /// non-finite cut-offs, malformed embeddings, or fewer than two signs (a margin
    /// between the best two signs needs at least two).
    public func validate() throws(BundleValidationError) {
        guard version == Self.supportedVersion else { throw .unsupportedVersion(version) }
        guard embeddingDim > 0 else { throw .invalidEmbeddingDimension(embeddingDim) }
        guard thresholds.similarity.isFinite, thresholds.margin.isFinite else { throw .nonFiniteThresholds }
        guard [quality.minPoseFraction, quality.minHandFraction].allSatisfy({ $0.isFinite && (0...1).contains($0) })
        else { throw .invalidQualityRequirements }

        for reference in references {
            guard reference.embedding.count == embeddingDim else {
                throw .embeddingDimensionMismatch(
                    referenceID: reference.id, expected: embeddingDim, actual: reference.embedding.count
                )
            }
            guard reference.embedding.allSatisfy(\.isFinite) else { throw .nonFiniteEmbedding(referenceID: reference.id) }
            guard reference.embedding.contains(where: { $0 != 0 }) else { throw .zeroNormEmbedding(referenceID: reference.id) }
        }

        let labelCount = Set(references.map(\.label)).count
        guard labelCount >= 2 else { throw .tooFewLabels(labelCount) }
    }
}
