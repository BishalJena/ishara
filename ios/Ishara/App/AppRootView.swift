import SwiftUI

/// Home → Get ready → Active call, following the workflow's four screens.
struct AppRootView: View {
    enum Route {
        case home
        case getReady
        case activeCall(ActiveCallViewModel)
    }

    @State private var route: Route
    @State private var setup: CallSetup = .demo
    private let options: DemoLaunchOptions

    init(options: DemoLaunchOptions) {
        self.options = options
        _route = State(initialValue: Self.initialRoute(for: options))
    }

    var body: some View {
        Group {
            switch route {
            case .home:
                HomeView(setup: setup) { chosen in
                    setup = chosen
                    route = .getReady
                }
            case .getReady:
                GetReadyView(timeScale: options.fakeTimeScale, onStart: startCall, onBack: { route = .home })
            case .activeCall(let model):
                ActiveCallView(model: model, onLeave: { route = .home })
            }
        }
    }

    private func startCall() {
        let driver = FakeCallDriver(options: options.fakeDriverOptions)
        route = .activeCall(ActiveCallViewModel(setup: setup, driver: driver))
    }

    private static func initialRoute(for options: DemoLaunchOptions) -> Route {
        #if DEBUG
        if let fixture = options.fixture {
            if fixture == .getReady { return .getReady }
            if let model = fixture.makeActiveCall() { return .activeCall(model) }
        }
        #endif
        return .home
    }
}
