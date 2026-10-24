import SwiftUI

@main
struct IsharaApp: App {
    var body: some Scene {
        WindowGroup {
            AppRootView(services: .current(options: .from()))
        }
    }
}
