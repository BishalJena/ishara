import CallSession
import Foundation

/// Backend settings baked into the app from the untracked `Config/Secrets.xcconfig`
/// (see `Config/Secrets.example.xcconfig`) through the Info.plist keys below. Nothing
/// real is committed; without them the app can only run the fake demo call.
struct AppConfig: Equatable {
    static let backendURLKey = "IsharaBackendURL"
    static let appTokenKey = "IsharaAppToken"

    enum Problem: Error, Equatable {
        case missingBackendURL
        case invalidBackendURL(String)
        case missingAppToken

        var message: String {
            switch self {
            case .missingBackendURL:
                "No backend URL. Set ISHARA_BACKEND_URL in ios/Ishara/Config/Secrets.xcconfig."
            case .invalidBackendURL(let value):
                "The backend URL \u{201C}\(value)\u{201D} isn't an http(s) URL. In xcconfig files write https:/$()/host."
            case .missingAppToken:
                "No app token. Set ISHARA_APP_TOKEN in ios/Ishara/Config/Secrets.xcconfig."
            }
        }
    }

    let backend: BackendConfig

    /// Reads and checks the two Info.plist values. Unexpanded `$(…)` placeholders count as missing.
    static func load(from info: [String: Any]) throws(Problem) -> AppConfig {
        let rawURL = value(info[backendURLKey])
        guard !rawURL.isEmpty else { throw .missingBackendURL }
        guard let url = URL(string: rawURL), let scheme = url.scheme?.lowercased(),
              ["http", "https"].contains(scheme), url.host() != nil
        else { throw .invalidBackendURL(rawURL) }
        let token = value(info[appTokenKey])
        guard !token.isEmpty else { throw .missingAppToken }
        return AppConfig(backend: BackendConfig(baseURL: url, appToken: token))
    }

    static func loadFromMainBundle() throws(Problem) -> AppConfig {
        try load(from: Bundle.main.infoDictionary ?? [:])
    }

    private static func value(_ raw: Any?) -> String {
        let text = (raw as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        return text.hasPrefix("$(") ? "" : text
    }
}
