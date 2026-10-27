import CallSession
import Foundation
import Observation

/// Decision D9, step 1: the user signs (or taps) what they need, adds the details the agent
/// may share, reads the brief the backend builds from exactly that, and approves it once by
/// starting the call. Editing anything after the brief was built hides it until it is built
/// again, so the approved brief always matches what is on screen.
@MainActor
@Observable
final class BriefModel {
    /// Time words to tap when signing is not convenient (the brief only carries chips).
    static let suggestions: [Sign] = [.today, .tomorrow, .morning, .afternoon, .evening, .later]

    let setup: CallSetup
    let recognition: any RecognitionController
    @ObservationIgnored let driver: any CallDriver

    var name: String
    var callback = ""
    var reason = ""
    /// Stay on the call and answer the agent's questions; off = the agent calls back instead.
    var attended = true

    private(set) var chips: [Sign] = []
    private(set) var candidate: Sign?
    private(set) var showsFramingHint = false
    /// The last sign was not recognised ("?"); cleared by the next sign or tap.
    private(set) var lastSignUnsure = false
    private(set) var cameraState: CameraState = .watching
    private(set) var isPreparing = false
    private(set) var failure: String?
    private var prepared: (request: BriefRequest, brief: Brief)?

    init(setup: CallSetup, driver: any CallDriver, recognition: any RecognitionController) {
        self.setup = setup
        self.driver = driver
        self.recognition = recognition
        name = setup.details.name
    }

    // MARK: Derived

    var request: BriefRequest {
        BriefRequest(
            purpose: setup.purpose, chips: chips,
            profile: Profile(name: Self.trimmed(name) ?? "", callback: Self.trimmed(callback), notes: Self.trimmed(reason)))
    }

    /// The brief for exactly what is on screen now, if it has been built.
    var brief: Brief? {
        guard let prepared, prepared.request == request else { return nil }
        return prepared.brief
    }

    var canPrepare: Bool { Self.trimmed(name) != nil && !isPreparing }

    /// The call to place once the user approves the brief shown.
    var approvedSetup: CallSetup? {
        guard let brief else { return nil }
        var approved = setup
        approved.details.name = Self.trimmed(name) ?? setup.details.name
        approved.delegation = Delegation(brief: brief, attended: attended)
        return approved
    }

    // MARK: Signing

    /// Turns recognition results into chips until the screen goes away.
    func run() async {
        for await event in recognition.signingEvents() { handle(event) }
    }

    func handle(_ event: RecognitionEvent) {
        guard case .result(let result) = event else {
            if case .camera(let state) = event { cameraState = state }
            return
        }
        candidate = nil
        showsFramingHint = false
        lastSignUnsure = false
        switch result {
        case .sign(let sign): add(sign)
        case .candidate(let sign): candidate = sign
        case .unsure: lastSignUnsure = true
        case .handLeftFrame:
            lastSignUnsure = true
            showsFramingHint = true
        }
    }

    func add(_ sign: Sign) {
        lastSignUnsure = false
        guard !chips.contains(sign), chips.count < ProtocolLimits.maxChips else { return }
        chips.append(sign)
    }

    func remove(_ sign: Sign) {
        chips.removeAll { $0 == sign }
    }

    func acceptCandidate() {
        guard let sign = candidate else { return }
        candidate = nil
        add(sign)
    }

    func dismissCandidate() {
        candidate = nil
    }

    // MARK: Brief

    /// `POST /briefs` for what is on screen. Nothing is dialled.
    func prepare() async {
        guard canPrepare else { return }
        let request = request
        isPreparing = true
        failure = nil
        defer { isPreparing = false }
        do {
            prepared = (request, try await driver.createBrief(request))
        } catch {
            failure = Self.describe(error)
        }
    }

    private static func trimmed(_ text: String) -> String? {
        let value = text.trimmingCharacters(in: .whitespacesAndNewlines)
        return value.isEmpty ? nil : value
    }

    private static func describe(_ error: Error) -> String {
        switch error as? BackendError {
        case .httpStatus(401)?: "The app token was refused. Check the app configuration."
        case .httpStatus(422)?: "The backend didn't accept these details. Check the name and callback number."
        case .httpStatus(let code)?: "The backend couldn't build the brief (HTTP \(code))."
        case .notHTTPResponse?: "The backend couldn't be reached."
        case nil: "The brief couldn't be built: \(error.localizedDescription)"
        }
    }
}
