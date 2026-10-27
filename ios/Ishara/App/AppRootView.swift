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
                        route = .notes(NotesModel(contactName: model.setup.contact.name, driver: model.driver))
                    } : nil
                )
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
        }
        #endif
        return .home
    }
}
