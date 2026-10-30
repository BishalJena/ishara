import SwiftUI

@main
struct IsharaApp: App {
    /// Made once: SwiftUI can rebuild `body` at any time, and a second set of services would
    /// bring a second call history that Home shows while the ended call updates the first.
    @State private var services = AppServices.current(options: .from())

    var body: some Scene {
        WindowGroup {
            AppRootView(services: services)
                .overlay(alignment: .topLeading) {
                    if services.options.film { FilmRecorderTick() }
                }
        }
    }
}

/// Film recording only (`-IsharaFilm 1`): `simctl io recordVideo` writes a frame only when
/// pixels change and loses real time while the screen is still, which would drift the film's
/// voices off the picture. Two pixels in the screen's extreme corner (under the rounded
/// display mask in the film's iPhone frame) flip every frame to keep it writing.
private struct FilmRecorderTick: View {
    var body: some View {
        TimelineView(.animation) { context in
            let odd = Int(context.date.timeIntervalSinceReferenceDate * 60) % 2 == 0
            Rectangle().fill(odd ? Color.black : Color.white).frame(width: 1, height: 1)
        }
        .ignoresSafeArea()
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}
