import SwiftUI

/// Home → Get ready → Active call, following the workflow's four screens.
struct AppRootView: View {
    enum Route {
        case home
        case getReady(any RecognitionController)
        case activeCall(ActiveCallViewModel)
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
                    setupProblem: services.setupProblem
                ) { chosen in
                    setup = chosen
                    route = .getReady(services.makeRecognition())
                }
            case .getReady(let recognition):
                GetReadyView(
                    recognition: recognition,
                    modeDescription: services.modeDescription,
                    onStart: { startCall(recognition: recognition) },
                    onBack: {
                        recognition.stop()
                        route = .home
                    }
                )
            case .activeCall(let model):
                ActiveCallView(model: model, onLeave: {
                    model.leave()
                    route = .home
                })
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
            if fixture == .getReady { return .getReady(ScriptedRecognitionController()) }
            if let model = fixture.makeActiveCall() { return .activeCall(model) }
        }
        #endif
        return .home
    }
}
