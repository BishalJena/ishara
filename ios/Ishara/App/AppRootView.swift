import SwiftUI

/// Home → Get ready → Active call, following the workflow's four screens. "Call for me"
/// (decision D9) goes Home → Get ready → Brief → Active call (delegated) → Notes.
struct AppRootView: View {
    enum Route {
        case home
        case getReady(any RecognitionController, delegated: Bool)
        case brief(BriefModel)
        case activeCall(ActiveCallViewModel)
        /// Steer flow: the one call screen (Ishara runs the call, the user steps in).
        case steerCall(ActiveCallViewModel)
        case notes(NotesModel)
    }

    /// Why the steer call couldn't be set up (creating its brief failed).
    @State private var steerProblem: String?
    /// What's typed on Home, kept across the call so "Back to the request" finds it.
    @State private var draft = SetupDraft()

    @State private var route: Route
    @State private var setup: CallSetup = .demo
    /// The last ended Call for me call's notes, followed by `CallFollowUp` outside any screen.
    @State private var notesFollowUp: (recordID: UUID, notes: NotesModel)?
    private let services: AppServices

    init(services: AppServices) {
        self.services = services
        _route = State(initialValue: Self.initialRoute(for: services))
    }

    var body: some View {
        Group {
            switch route {
            case .home where services.options.flow == .steer:
                SetupView(
                    modeDescription: services.modeDescription,
                    setupProblem: services.setupProblem ?? steerProblem,
                    history: services.history,
                    draft: draft,
                    onCall: { chosen in startSteerCall(chosen) }
                )
            case .steerCall(let model):
                SteerCallView(
                    model: model,
                    onLeave: {
                        model.leave()
                        route = .home
                    },
                    onShowNotes: {
                        model.leave()
                        let notes = followUp(model) ?? NotesModel(contactName: model.setup.contact.name, driver: model.driver)
                        notes.start()
                        route = .notes(notes)
                    }
                )
                .onChange(of: model.isCallOver) { _, isOver in
                    if isOver { followUp(model) }
                }
            case .home:
                HomeView(
                    setup: setup,
                    modeDescription: services.modeDescription,
                    setupProblem: services.setupProblem,
                    history: services.history,
                    onCall: { chosen in
                        setup = chosen
                        route = .getReady(services.makeRecognition(), delegated: false)
                    },
                    onCallForMe: { chosen in
                        setup = chosen
                        route = .getReady(services.makeRecognition(), delegated: true)
                    }
                )
            case .getReady(let recognition, let delegated):
                GetReadyView(
                    recognition: recognition,
                    modeDescription: services.modeDescription,
                    startTitle: delegated ? "I'm ready, sign my request" : GetReadyView.callTitle,
                    onStart: {
                        if delegated {
                            let driver = services.makeDriver(recognition: recognition)
                            route = .brief(BriefModel(setup: setup, driver: driver, recognition: recognition))
                        } else {
                            startCall(recognition: recognition)
                        }
                    },
                    onBack: {
                        recognition.stop()
                        route = .home
                    }
                )
            case .brief(let model):
                BriefView(
                    model: model,
                    modeDescription: services.modeDescription,
                    onApprove: { approved in
                        route = .activeCall(ActiveCallViewModel(
                            setup: approved, driver: model.driver, recognition: model.recognition))
                    },
                    onBack: {
                        model.recognition.stop()
                        route = .home
                    }
                )
            case .activeCall(let model):
                ActiveCallView(
                    model: model,
                    onLeave: {
                        model.leave()
                        route = .home
                    },
                    onShowNotes: model.isDelegated ? {
                        model.leave()
                        // A call that was never placed has no follow-up; its notes say why.
                        let notes = followUp(model) ?? NotesModel(contactName: model.setup.contact.name, driver: model.driver)
                        notes.start()
                        route = .notes(notes)
                    } : nil
                )
                // Saved and followed as soon as the call is over, whatever the user does next.
                .onChange(of: model.isCallOver) { _, isOver in
                    if isOver { followUp(model) }
                }
            case .notes(let model) where services.options.flow == .steer:
                SteerGistView(
                    model: model,
                    onDone: {
                        draft.clear()
                        route = .home
                    },
                    onCallAgain: { startSteerCall(setup) }
                )
            case .notes(let model):
                NotesView(model: model, onDone: { route = .home })
            }
        }
    }

    /// The ended call's follow-up, started once per call.
    @discardableResult
    private func followUp(_ call: ActiveCallViewModel) -> NotesModel? {
        if let notesFollowUp, notesFollowUp.recordID == call.recordID { return notesFollowUp.notes }
        let notes = CallFollowUp.callEnded(call, history: services.history)
        if let notes { notesFollowUp = (call.recordID, notes) }
        return notes
    }

    private func startCall(recognition: any RecognitionController) {
        let driver = services.makeDriver(recognition: recognition)
        route = .activeCall(ActiveCallViewModel(setup: setup, driver: driver, recognition: recognition))
    }

    /// Steer flow: the typed request becomes the brief (the one approval), then the call
    /// starts with it. Signing is only set up if the user taps the sign button on the call.
    private func startSteerCall(_ chosen: CallSetup) {
        steerProblem = nil
        let recognition = services.makeRecognition()
        let driver = services.makeDriver(recognition: recognition)
        Task { @MainActor in
            do {
                let brief = try await driver.createBrief(chosen.steerBriefRequest)
                var ready = chosen
                ready.delegation = Delegation(brief: brief, attended: false, mode: .steer)
                setup = ready
                route = .steerCall(ActiveCallViewModel(setup: ready, driver: driver, recognition: recognition))
            } catch {
                driver.close()
                steerProblem = "Couldn't set up the call: \(error.localizedDescription)"
                route = .home  // "Call again" starts from the gist; the problem shows on Home
            }
        }
    }

    private static func initialRoute(for services: AppServices) -> Route {
        #if DEBUG
        if let fixture = services.options.fixture {
            if fixture == .getReady { return .getReady(ScriptedRecognitionController(), delegated: false) }
            if let model = fixture.makeActiveCall() { return .activeCall(model) }
            if let model = fixture.makeNotes() {
                model.start()
                return .notes(model)
            }
        }
        #endif
        return .home
    }
}
