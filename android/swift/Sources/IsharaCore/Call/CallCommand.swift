import CallSession
import Foundation

/// One `TurnStore` method call from Kotlin: `{"op": <method name>, ...arguments}`.
enum CallCommand: Decodable {
    case add(ChipDTO)
    case remove(chipID: UUID)
    case useQuickReply(QuickReply)
    case clear
    case send
    case resend
    case stop
    case end
    case setPresent(Bool)
    case approveProposal
    case startComposing
    case stopComposing
    case say(String)
    case holdPreview
    case answer(AskChoice)
    case answerIfAsked(Sign)
    case connectionLost

    private enum CodingKeys: String, CodingKey {
        case op, chip, chipId, reply, present, text, choice, sign
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let op = try container.decode(String.self, forKey: .op)
        switch op {
        case "add": self = .add(try container.decode(ChipDTO.self, forKey: .chip))
        case "remove": self = .remove(chipID: try container.decode(UUID.self, forKey: .chipId))
        case "useQuickReply":
            let reply = try container.decode(String.self, forKey: .reply)
            guard let quickReply = QuickReply.allCases.first(where: { $0.wireName == reply }) else {
                throw BridgeError.invalidArgument("quick reply \(reply)")
            }
            self = .useQuickReply(quickReply)
        case "clear": self = .clear
        case "send": self = .send
        case "resend": self = .resend
        case "stop": self = .stop
        case "end": self = .end
        case "setPresent": self = .setPresent(try container.decode(Bool.self, forKey: .present))
        case "approveProposal": self = .approveProposal
        case "startComposing": self = .startComposing
        case "stopComposing": self = .stopComposing
        case "say": self = .say(try container.decode(String.self, forKey: .text))
        case "holdPreview": self = .holdPreview
        case "answer": self = .answer(try container.decode(AskChoice.self, forKey: .choice))
        case "answerIfAsked": self = .answerIfAsked(try container.decode(Sign.self, forKey: .sign))
        case "connectionLost": self = .connectionLost
        default: throw BridgeError.invalidArgument("op \(op)")
        }
    }

    /// Runs the command; the result is the method's Bool return value, when it has one.
    @MainActor
    func run(on store: TurnStore) throws -> Bool? {
        switch self {
        case let .add(chip): return store.add(try chip.chip())
        case let .remove(chipID):
            if let chip = store.chips.first(where: { $0.id == chipID }) { store.remove(chip) }
        case let .useQuickReply(reply): store.useQuickReply(reply)
        case .clear: store.clear()
        case .send: store.send()
        case .resend: store.resend()
        case .stop: store.stop()
        case .end: store.end()
        case let .setPresent(present): store.setPresent(present)
        case .approveProposal: store.approveProposal()
        case .startComposing: store.startComposing()
        case .stopComposing: store.stopComposing()
        case let .say(text): return store.say(text)
        case .holdPreview: store.holdPreview()
        case let .answer(choice): return store.answer(choice)
        case let .answerIfAsked(sign): return store.answerIfAsked(sign)
        case .connectionLost: store.connectionLost()
        }
        return nil
    }
}

extension QuickReply {
    /// The name Kotlin uses (the Swift case name).
    var wireName: String {
        switch self {
        case .yes: "yes"
        case .no: "no"
        case .wait: "wait"
        case .repeat: "repeat"
        }
    }
}
