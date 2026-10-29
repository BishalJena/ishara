import SwiftUI

/// Home → Get ready → Active call, following the workflow's four screens. "Call for me"
/// (decision D9) goes Home → Get ready → Brief → Active call (delegated) → Notes.
struct AppRootView: View {
    enum Route {
        case home
        case getReady(any RecognitionController, delegated: Bool)
        case brief(BriefModel)
        case activeCall(ActiveCallViewModel)
        case notes(NotesModel)
    }

    @State private var route: Route
    @State private var setup: CallSetup = .demo
    private let services: AppServices

    init(services: AppServices) {
        self.services = services
        _route = State(initialValue: Self.initialRoute(for: services))
    }

    var body: some View {
        Group {
            switch route {
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
                        let history = services.history
                        let notes = NotesModel(
                            contactName: model.setup.contact.name, driver: model.driver,
                            onNotes: { history.update(model.recordID, notes: $0) })
                        notes.start()
                        route = .notes(notes)
                    } : nil
                )
                // Saved as soon as the call is over, before the notes (if any) are loaded.
                .onChange(of: model.isCallOver) { _, isOver in
                    if isOver, let record = model.record { services.history.save(record) }
                }
            case .notes(let model):
                NotesView(model: model, onDone: { route = .home })
            }
        }
    }

    private func startCall(recognition: any RecognitionController) {
        let driver = services.makeDriver(recognition: recognition)
        route = .activeCall(ActiveCallViewModel(setup: setup, driver: driver, recognition: recognition))
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
