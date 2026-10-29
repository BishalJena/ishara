import SwiftUI

@main
struct IsharaApp: App {
    /// Made once: SwiftUI can rebuild `body` at any time, and a second set of services would
    /// bring a second call history that Home shows while the ended call updates the first.
    @State private var services = AppServices.current(options: .from())

    var body: some Scene {
        WindowGroup {
            AppRootView(services: services)
        }
    }
}
