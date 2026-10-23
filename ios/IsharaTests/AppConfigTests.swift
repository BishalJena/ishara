import CallSession
import XCTest
@testable import Ishara

final class AppConfigTests: XCTestCase {
    private func load(url: String?, token: String?) throws(AppConfig.Problem) -> AppConfig {
        var info: [String: Any] = [:]
        info[AppConfig.backendURLKey] = url
        info[AppConfig.appTokenKey] = token
        return try AppConfig.load(from: info)
    }

    private func problem(url: String?, token: String?) -> AppConfig.Problem? {
        do {
            _ = try load(url: url, token: token)
            return nil
        } catch {
            return error
        }
    }

    func testReadsBackendURLAndToken() throws {
        let config = try load(url: "https://ishara.example.test", token: "secret")

        XCTAssertEqual(config.backend.baseURL.absoluteString, "https://ishara.example.test")
        XCTAssertEqual(config.backend.webSocketBaseURL.absoluteString, "wss://ishara.example.test")
        XCTAssertEqual(config.backend.appToken, "secret")
    }

    func testLocalHTTPBackendIsAllowed() throws {
        let config = try load(url: "http://127.0.0.1:8000", token: "secret")
        XCTAssertEqual(config.backend.webSocketBaseURL.absoluteString, "ws://127.0.0.1:8000")
    }

    func testMissingOrUnexpandedValuesAreReported() {
        XCTAssertEqual(problem(url: nil, token: "secret"), .missingBackendURL)
        XCTAssertEqual(problem(url: "  ", token: "secret"), .missingBackendURL)
        XCTAssertEqual(problem(url: "$(ISHARA_BACKEND_URL)", token: "secret"), .missingBackendURL)
        XCTAssertEqual(problem(url: "https://ishara.example.test", token: nil), .missingAppToken)
        XCTAssertEqual(problem(url: "https://ishara.example.test", token: "$(ISHARA_APP_TOKEN)"), .missingAppToken)
    }

    func testURLsWithoutHTTPSchemeOrHostAreRejected() {
        // What an xcconfig leaves when `//` starts a comment: "https:".
        XCTAssertEqual(problem(url: "https:", token: "secret"), .invalidBackendURL("https:"))
        XCTAssertEqual(problem(url: "ftp://ishara.example.test", token: "secret"), .invalidBackendURL("ftp://ishara.example.test"))
        XCTAssertEqual(problem(url: "ishara.example.test", token: "secret"), .invalidBackendURL("ishara.example.test"))
    }
}
