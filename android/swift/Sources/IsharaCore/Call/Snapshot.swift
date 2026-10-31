import CallSession
import Foundation

/// Every observable `TurnStore` property (and the derived ones the screens read), as JSON for
/// Kotlin. Enums with associated values become `{"kind": ..., ...}`; dates are epoch seconds.
struct CallSnapshot: Encodable {
    let state: CallState
    let connectedAt: Double?
    let captions: [CaptionDTO]
    let currentTurnId: String
    let chips: [ChipDTO]
    let draft: DraftDTO?
    let sending: SendingDTO
    let stopProgress: String
    let lastError: ErrorDTO?
    let notice: String?
    let openQuestion: OpenQuestionDTO?
    let proposal: ProposalDTO?
    let isComposing: Bool
    let followUps: [String]
    let steppedIn: Int
    let canSend: Bool
    let canResend: Bool
    let unspokenText: String?
    let isStopRequested: Bool
    let recognisedSigns: [Sign]

    @MainActor
    init(_ store: TurnStore) {
        state = store.state
        connectedAt = store.connectedAt?.timeIntervalSince1970
        captions = store.captions.map(CaptionDTO.init)
        currentTurnId = store.currentTurnID.rawValue
        chips = store.chips.map(ChipDTO.init)
        draft = store.draft.map(DraftDTO.init)
        sending = SendingDTO(store.sending)
        stopProgress = switch store.stopProgress {
        case .none: "none"
        case .requested: "requested"
        case .tooLate: "tooLate"
        }
        lastError = store.lastError.map { ErrorDTO(code: $0.code, message: $0.message) }
        notice = store.notice
        openQuestion = store.openQuestion.map(OpenQuestionDTO.init)
        proposal = store.proposal.map(ProposalDTO.init)
        isComposing = store.isComposing
        followUps = store.followUps
        steppedIn = store.steppedIn
        canSend = store.canSend
        canResend = store.canResend
        unspokenText = store.unspokenText
        isStopRequested = store.isStopRequested
        recognisedSigns = store.recognisedSigns
    }

    struct CaptionDTO: Encodable {
        let text: String
        let at: Double
        let speaker: String

        init(_ caption: Caption) {
            text = caption.text
            at = caption.at.timeIntervalSince1970
            speaker = switch caption.speaker {
            case .receptionist: "receptionist"
            case .agent: "agent"
            case .user: "user"
            }
        }
    }

    struct DraftDTO: Encodable {
        let text: String
        let origin: String

        init(_ draft: Draft) {
            text = draft.text
            origin = switch draft.origin {
            case .llm: "llm"
            case .template: "template"
            case .quickReply: "quickReply"
            }
        }
    }

    struct SendingDTO: Encodable {
        let kind: String
        var turnId: String?
        var text: String?

        init(_ phase: SendingPhase) {
            switch phase {
            case .idle: kind = "idle"
            case let .speaking(turnID, text):
                kind = "speaking"
                turnId = turnID.rawValue
                self.text = text
            case .delivered: kind = "delivered"
            case .deliveredDespiteStop: kind = "deliveredDespiteStop"
            case let .notDelivered(text):
                kind = "notDelivered"
                self.text = text
            case let .stopped(text):
                kind = "stopped"
                self.text = text
            }
        }
    }

    struct ErrorDTO: Encodable {
        let code: String
        let message: String
    }

    struct OpenQuestionDTO: Encodable {
        let askId: String
        let question: String
        let options: [AskOption]
        let fallback: String
        let timeoutS: Double
        let askedAt: Double

        init(_ question: OpenQuestion) {
            askId = question.askID
            self.question = question.question
            options = question.options
            fallback = question.fallback
            timeoutS = question.timeoutS
            askedAt = question.askedAt.timeIntervalSince1970
        }
    }

    struct ProposalDTO: Encodable {
        let turnId: String
        let text: String
        let windowS: Double
        let origin: ProposalOrigin
        let shownAt: Double

        init(_ proposal: Proposal) {
            turnId = proposal.turnID.rawValue
            text = proposal.text
            windowS = proposal.windowS
            origin = proposal.origin
            shownAt = proposal.shownAt.timeIntervalSince1970
        }
    }
}

/// A chip as `{"id": UUID, "kind": {"kind": "recognised", "sign": ...} | {"kind": "unsure"}}`,
/// both in snapshots and in the `add` command.
struct ChipDTO: Codable {
    struct Kind: Codable {
        let kind: String
        var sign: Sign?
    }

    let id: UUID
    let kind: Kind

    init(_ chip: Chip) {
        id = chip.id
        kind = switch chip.kind {
        case let .recognised(sign): Kind(kind: "recognised", sign: sign)
        case .unsure: Kind(kind: "unsure")
        }
    }

    func chip() throws -> Chip {
        switch (kind.kind, kind.sign) {
        case let ("recognised", sign?): Chip(id: id, kind: .recognised(sign))
        case ("unsure", nil): Chip(id: id, kind: .unsure)
        default: throw BridgeError.invalidArgument("chip kind \(kind.kind)")
        }
    }
}

enum BridgeError: Error, CustomStringConvertible {
    case invalidArgument(String)
    case unknownSession(Int32)
    case notLocal(Int32)
    case backendNotConfigured

    var description: String {
        switch self {
        case .backendNotConfigured: "configureBackend has not been called"
        case let .invalidArgument(detail): "invalid argument: \(detail)"
        case let .unknownSession(id): "no call session \(id)"
        case let .notLocal(id): "call session \(id) is live; only local sessions take server messages from Kotlin"
        }
    }
}
