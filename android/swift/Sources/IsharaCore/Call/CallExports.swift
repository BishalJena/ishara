import CAndroidBridge
import CallSession
import Foundation
import Synchronization

// JNI entry points for the call layer on `ai.ishara.demo.core.IsharaCore`.
//
// Sync functions run TurnStore code and must be called on the Android main thread (Swift's
// main actor); otherwise they throw IllegalStateException. Async functions take a Kotlin
// request id and later emit `{"type":"result","requestId":…,"ok":…,"value"|"error":…}`.

private let backendConfig = Mutex<BackendConfig?>(nil)

@_cdecl("Java_ai_ishara_demo_core_IsharaCore_configureBackend")
public func configureBackend(_ env: JNIEnvPointer, _ this: jobject?, _ baseURL: jstring?, _ appToken: jstring?) {
    guard let baseURL, let appToken else { return env.throwNew("java/lang/NullPointerException", "configureBackend") }
    let rawURL = env.string(baseURL)
    guard let url = URL(string: rawURL), url.scheme != nil, url.host() != nil else {
        return env.throwNew("java/lang/IllegalArgumentException", "not a backend URL: \(rawURL)")
    }
    let config = BackendConfig(baseURL: url, appToken: env.string(appToken))
    backendConfig.withLock { $0 = config }
}

/// `{"initialState": CallState}` → `{"sessionId": Int, "snapshot": CallSnapshot}`.
@_cdecl("Java_ai_ishara_demo_core_IsharaCore_startLocalSession")
public func startLocalSession(_ env: JNIEnvPointer, _ this: jobject?, _ requestJSON: jstring?) -> jstring? {
    onMainActor(env, requestJSON) { request in
        let initialState = try JSONDecoder().decode(LocalStart.self, from: Data(request.utf8)).initialState
        let session = CallSessions.shared.startLocal(initialState: initialState)
        return try wireJSON(SessionStart(sessionId: session.id, callId: nil, snapshot: session.snapshot))
    }
}

/// `StartCallRequest` wire JSON → result `{"sessionId", "callId", "snapshot"}`.
@_cdecl("Java_ai_ishara_demo_core_IsharaCore_startLiveCall")
public func startLiveCall(_ env: JNIEnvPointer, _ this: jobject?, _ requestID: jlong, _ requestJSON: jstring?) {
    guard let request: StartCallRequest = decodeArgument(env, requestJSON) else { return }
    completeLater(requestID) {
        let session = try await CallSessions.shared.startLive(config: try configured(), request: request)
        guard case let .live(call, _) = session.kind else { preconditionFailure("startLive made a local session") }
        return try wireJSON(SessionStart(sessionId: session.id, callId: call.callID, snapshot: session.snapshot))
    }
}

/// `BriefRequest` wire JSON → result `Brief` wire JSON.
@_cdecl("Java_ai_ishara_demo_core_IsharaCore_createBrief")
public func createBrief(_ env: JNIEnvPointer, _ this: jobject?, _ requestID: jlong, _ requestJSON: jstring?) {
    guard let request: BriefRequest = decodeArgument(env, requestJSON) else { return }
    completeLater(requestID) {
        try wireJSON(try await BackendClient(config: try configured()).createBrief(request))
    }
}

/// Call id → result `CallNotes` wire JSON.
@_cdecl("Java_ai_ishara_demo_core_IsharaCore_fetchNotes")
public func fetchNotes(_ env: JNIEnvPointer, _ this: jobject?, _ requestID: jlong, _ callID: jstring?) {
    guard let callID else { return env.throwNew("java/lang/NullPointerException", "callId") }
    let id = env.string(callID)
    completeLater(requestID) {
        try wireJSON(try await BackendClient(config: try configured()).notes(callID: id))
    }
}

/// Reopens a live session's socket (`LiveCall.connect()`); result value null.
@_cdecl("Java_ai_ishara_demo_core_IsharaCore_connect")
public func connect(_ env: JNIEnvPointer, _ this: jobject?, _ requestID: jlong, _ sessionID: jint) {
    completeLater(requestID) {
        await (try liveCall(sessionID)).connect()
        return nil
    }
}

/// Result `{"kind": "dropped"|"unauthorized"|"unknownCall"|"replaced", "allowsReconnect": Bool}`,
/// or null while the socket is open.
@_cdecl("Java_ai_ishara_demo_core_IsharaCore_lastClose")
public func lastClose(_ env: JNIEnvPointer, _ this: jobject?, _ requestID: jlong, _ sessionID: jint) {
    completeLater(requestID) {
        guard let close = await (try liveCall(sessionID)).lastClose else { return nil }
        return try wireJSON(SocketCloseDTO(close))
    }
}

/// `{"op": …}` (see `CallCommand`) → `{"ok": true}` or `{"ok": true, "value": Bool}`.
@_cdecl("Java_ai_ishara_demo_core_IsharaCore_command")
public func command(_ env: JNIEnvPointer, _ this: jobject?, _ sessionID: jint, _ commandJSON: jstring?) -> jstring? {
    onMainActor(env, commandJSON) { json in
        let command = try JSONDecoder().decode(CallCommand.self, from: Data(json.utf8))
        let value = try command.run(on: CallSessions.shared.session(sessionID).store)
        return value.map { #"{"ok":true,"value":\#($0)}"# } ?? #"{"ok":true}"#
    }
}

/// Feeds a backend `ServerMessage` (wire JSON) to a local session's store.
@_cdecl("Java_ai_ishara_demo_core_IsharaCore_receive")
public func receive(_ env: JNIEnvPointer, _ this: jobject?, _ sessionID: jint, _ messageJSON: jstring?) {
    _ = onMainActor(env, messageJSON) { json in
        let session = try CallSessions.shared.session(sessionID)
        guard case .local = session.kind else { throw BridgeError.notLocal(sessionID) }
        session.store.receive(try WireCoding.decodeServerMessage(json))
        return ""
    }
}

/// Stops a session's snapshots, disconnects a live call's socket and frees it. Sends nothing.
@_cdecl("Java_ai_ishara_demo_core_IsharaCore_closeSession")
public func closeSession(_ env: JNIEnvPointer, _ this: jobject?, _ sessionID: jint) {
    _ = onMainActor(env, nil) { _ in
        CallSessions.shared.close(sessionID)
        return ""
    }
}

// MARK: Helpers

private struct LocalStart: Decodable {
    let initialState: CallState
}

private struct SessionStart: Encodable {
    let sessionId: Int32
    let callId: String?
    let snapshot: CallSnapshot
}

private struct SocketCloseDTO: Encodable {
    let kind: String
    let allowsReconnect: Bool

    init(_ close: CallSocketClose) {
        kind = switch close {
        case .dropped: "dropped"
        case .unauthorized: "unauthorized"
        case .unknownCall: "unknownCall"
        case .replaced: "replaced"
        }
        allowsReconnect = close.allowsReconnect
    }
}

/// The error of a failed async call. `kind` keeps the distinctions the screens make.
private struct ResultError: Encodable {
    let kind: String
    var status: Int?
    let message: String

    init(_ error: any Error) {
        message = (error as? LocalizedError)?.errorDescription ?? String(describing: error)
        switch error {
        case let BackendError.httpStatus(code):
            status = code
            kind = switch code {
            case 401: "unauthorized"
            case 403: "forbidden"
            case 404: "notFound"
            case 422: "validation"
            case 500...: "server"
            default: "http"
            }
        case BackendError.notHTTPResponse: kind = "notHTTPResponse"
        case is DecodingError: kind = "decoding"
        case is URLError: kind = "transport"
        case BridgeError.backendNotConfigured: kind = "notConfigured"
        case BridgeError.unknownSession, BridgeError.notLocal: kind = "unknownSession"
        default: kind = "unexpected"
        }
    }
}

private func configured() throws -> BackendConfig {
    guard let config = backendConfig.withLock({ $0 }) else { throw BridgeError.backendNotConfigured }
    return config
}

@MainActor
private func liveCall(_ sessionID: Int32) throws -> LiveCall {
    guard case let .live(call, _) = try CallSessions.shared.session(sessionID).kind else {
        throw BridgeError.unknownSession(sessionID)
    }
    return call
}

private func wireJSON(_ value: some Encodable) throws -> String {
    String(decoding: try WireCoding.makeEncoder().encode(value), as: UTF8.self)
}

private func decodeArgument<T: Decodable>(_ env: JNIEnvPointer, _ json: jstring?) -> T? {
    guard let json else {
        env.throwNew("java/lang/NullPointerException", "request JSON")
        return nil
    }
    do {
        return try JSONDecoder().decode(T.self, from: Data(env.string(json).utf8))
    } catch {
        env.throwNew("java/lang/IllegalArgumentException", String(describing: error))
        return nil
    }
}

/// Runs `operation` on the main actor and emits its result event; `value` is raw JSON.
private func completeLater(_ requestID: jlong, _ operation: @escaping @MainActor () async throws -> String?) {
    Task { @MainActor in
        let event: String
        do {
            let value = try await operation() ?? "null"
            event = #"{"type":"result","requestId":\#(requestID),"ok":true,"value":\#(value)}"#
        } catch {
            let failure = (try? wireJSON(ResultError(error))) ?? #"{"kind":"unexpected","message":""}"#
            event = #"{"type":"result","requestId":\#(requestID),"ok":false,"error":\#(failure)}"#
        }
        EventSink.emit(event)
    }
}

/// Runs `body` synchronously on the main actor with the string argument (empty for nil).
/// Throws IllegalStateException off the main thread and IllegalArgumentException when
/// `body` fails.
private func onMainActor(
    _ env: JNIEnvPointer, _ argument: jstring?, _ body: @MainActor (String) throws -> String
) -> jstring? {
    guard gettid() == getpid() else {
        env.throwNew("java/lang/IllegalStateException", "call sessions must be used on the main thread")
        return nil
    }
    let text = argument.map { env.string($0) } ?? ""
    let result: Result<String, any Error> = MainActor.assumeIsolated {
        Result { try body(text) }
    }
    switch result {
    case let .success(json): return env.newString(json)
    case let .failure(error):
        env.throwNew("java/lang/IllegalArgumentException", String(describing: error))
        return nil
    }
}
