# Ishara iOS app

SwiftUI demo app (iOS 17+, iPhone, portrait). For now it runs the four workflow
screens on fake data: `FakeCallDriver` plays the PLAN §1 clinic call on timers, so
you can click through the whole demo in the simulator. It has no backend, camera or
real call yet.

## Open

```sh
open ios/Ishara.xcodeproj
```

Pick the **Ishara** scheme and an iPhone simulator, then Run. To run on a device,
choose your own team under Signing & Capabilities. Don't commit it:
`DEVELOPMENT_TEAM` stays empty in Git.

## Regenerate the project

`ios/project.yml` is the source of truth. Edit it, then:

```sh
brew install xcodegen   # once
xcodegen generate --spec ios/project.yml
```

Commit `project.yml` and `Ishara.xcodeproj` together.

## Build and test

```sh
xcrun simctl list devices available | grep iPhone   # pick a simulator name
xcodebuild -project ios/Ishara.xcodeproj -scheme Ishara \
  -destination 'platform=iOS Simulator,name=iPhone 17' test
```

This runs the unit tests (`IsharaTests`) and the UI tests (`IsharaUITests`),
which walk the whole PLAN §1 call on the fake driver at `-IsharaFakeTimeScale 0.5`
(about a minute). Add `-only-testing:IsharaTests` for just the unit tests.

If `xcode-select` points at the Command Line Tools, prefix the command with
`DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer`.

## Demo switches (launch arguments)

Set these in the scheme (Run → Arguments) or pass them to `xcrun simctl launch`:

| Argument | Effect |
|---|---|
| `-IsharaFakeNotDelivered YES` | The first SEND of turn 2 comes back "not delivered", so you have to tap SEND again |
| `-IsharaFakeTimeScale 0.5` | Runs the Get ready checks and the fake call twice as fast |
| `-IsharaFixture <name>` | Debug builds only. Opens a prepared state: `home`, `getReady`, `signing`, `speaking`, `delivered`, `notDelivered`, `ended`, `connectionLost` |

Screenshot example:

```sh
xcrun simctl launch booted ai.ishara.demo -IsharaFixture signing
xcrun simctl io booted screenshot /tmp/ishara-signing.png
```

## Layout

| Path | What |
|---|---|
| `Ishara/Models` | Call setup, turns, chips, drafts, quick replies |
| `Ishara/Call` | `CallDriver` boundary, `ActiveCallViewModel` (SEND safety rules), `FakeCallDriver` and the demo script |
| `Ishara/Views` | Home, Get ready, Active call and shared components |
| `Ishara/App` | App entry, navigation, launch options and Debug fixtures |
| `IsharaTests` | XCTest for the view model, get-ready model and demo script |
| `IsharaUITests` | XCUITest that clicks through the §1 demo call, plus the not-delivered retry |
