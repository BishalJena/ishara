import CAndroidBridge
import CallSession
import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
import Synchronization

/// CallSession's call socket on Android, run by OkHttp in Kotlin (`OkHttpWebSockets`).
///
/// Swift's own `URLSessionWebSocketTask` on Android turns any close code it has no case for
/// into 1003, so the backend's 4401 / 4404 / 4409 would look like plain drops. OkHttp reports
/// the server's code as sent. Semantics match `URLSessionWebSocketTransport`.
final class KotlinWebSocketTransport: WebSocketTransport {
    private struct State {
        var socketID: Int64?
        var closeCode: Int?
    }

    private let state = Mutex(State())

    /// Opens a socket for `request` with all its headers, closing any previous one. The
    /// stream finishes when the socket closes for any reason.
    func connect(_ request: URLRequest) async -> AsyncStream<String> {
        close()
        let id = KotlinSockets.nextID()
        state.withLock { $0 = State(socketID: id, closeCode: nil) }
        let (frames, continuation) = AsyncStream<String>.makeStream()
        continuation.onTermination = { _ in KotlinSockets.close(id) }
        let socket = KotlinSockets.Socket(
            receive: { continuation.yield($0) },
            closed: { [weak self] code in
                // A socket replaced by `connect` must not overwrite the new socket's code.
                self?.state.withLock { if $0.socketID == id { $0.closeCode = code } }
                continuation.finish()
            })
        KotlinSockets.open(
            id, url: request.url?.absoluteString ?? "", headers: request.allHTTPHeaderFields ?? [:], socket: socket)
        return frames
    }

    func send(_ text: String) async throws {
        guard let id = state.withLock({ $0.socketID }), KotlinSockets.send(id, text) else {
            throw WebSocketTransportError.notConnected
        }
    }

    func close() {
        let id = state.withLock { state -> Int64? in
            defer { state.socketID = nil }
            return state.socketID
        }
        if let id { KotlinSockets.close(id) }
    }

    /// The server's close code once the stream has finished; nil while open, or when the
    /// socket died without a close frame.
    var closeCode: Int? {
        state.withLock { $0.closeCode }
    }
}

/// The open sockets by id, and the Kotlin object (`OkHttpWebSockets`) that runs them. Kotlin
/// reports frames and closes through `socketMessage` / `socketClosed`, on OkHttp's threads.
enum KotlinSockets {
    struct Socket: Sendable {
        let receive: @Sendable (String) -> Void
        let closed: @Sendable (Int?) -> Void
    }

    private struct Bridge: @unchecked Sendable {
        let object: jobject
        let connect: jmethodID
        let send: jmethodID
        let close: jmethodID
    }

    private static let bridge = Mutex<Bridge?>(nil)
    private static let sockets = Mutex<[Int64: Socket]>([:])
    private static let lastID = Atomic<Int64>(0)

    /// Installed once per process; later calls are ignored so in-flight calls keep a valid reference.
    static func install(_ env: JNIEnvPointer, _ object: jobject) {
        guard bridge.withLock({ $0 == nil }) else { return }
        guard let objectClass = env.jni.GetObjectClass(env, object) else { return }
        defer { env.jni.DeleteLocalRef(env, objectClass) }
        guard let connect = env.jni.GetMethodID(env, objectClass, "connect", "(JLjava/lang/String;Ljava/lang/String;)V"),
              let send = env.jni.GetMethodID(env, objectClass, "send", "(JLjava/lang/String;)Z"),
              let close = env.jni.GetMethodID(env, objectClass, "close", "(J)V"),
              let global = env.jni.NewGlobalRef(env, object)
        else { return }
        bridge.withLock { $0 = Bridge(object: global, connect: connect, send: send, close: close) }
    }

    static func nextID() -> Int64 {
        lastID.add(1, ordering: .relaxed).newValue
    }

    static func open(_ id: Int64, url: String, headers: [String: String], socket: Socket) {
        sockets.withLock { $0[id] = socket }
        // Header names and values are strings, so this always encodes.
        let headersJSON = String(decoding: try! JSONEncoder().encode(headers), as: UTF8.self)
        let opened = call { env, bridge in
            var arguments = [jvalue(j: id), jvalue(l: env.newString(url)), jvalue(l: env.newString(headersJSON))]
            env.jni.CallVoidMethodA(env, bridge.object, bridge.connect, &arguments)
        }
        if !opened { take(id)?.closed(nil) }
    }

    static func send(_ id: Int64, _ text: String) -> Bool {
        var accepted = false
        let called = call { env, bridge in
            var arguments = [jvalue(j: id), jvalue(l: env.newString(text))]
            accepted = env.jni.CallBooleanMethodA(env, bridge.object, bridge.send, &arguments) != 0
        }
        return called && accepted
    }

    /// Finishes the socket's stream (recording no close code) and closes it in Kotlin.
    static func close(_ id: Int64) {
        take(id)?.closed(nil)
        _ = call { env, bridge in
            var arguments = [jvalue(j: id)]
            env.jni.CallVoidMethodA(env, bridge.object, bridge.close, &arguments)
        }
    }

    static func received(_ id: Int64, _ text: String) {
        sockets.withLock { $0[id] }?.receive(text)
    }

    static func closedByPeer(_ id: Int64, code: Int?) {
        take(id)?.closed(code)
    }

    private static func take(_ id: Int64) -> Socket? {
        sockets.withLock { $0.removeValue(forKey: id) }
    }

    /// Runs `body` with the bridge; false when it isn't installed or the Kotlin method threw.
    private static func call(_ body: (JNIEnvPointer, Bridge) -> Void) -> Bool {
        guard let current = bridge.withLock({ $0 }) else {
            log(.error, "the OkHttp socket bridge is not installed")
            return false
        }
        var succeeded = false
        withJNIEnv { env in
            guard env.jni.PushLocalFrame(env, 4) == JNI_OK else { return }
            defer { _ = env.jni.PopLocalFrame(env, nil) }
            body(env, current)
            if env.jni.ExceptionCheck(env) != 0 {
                log(.error, "OkHttpWebSockets threw")
                env.jni.ExceptionDescribe(env)
                env.jni.ExceptionClear(env)
                return
            }
            succeeded = true
        }
        return succeeded
    }
}

@_cdecl("Java_ai_ishara_demo_core_IsharaCore_setSocketBridge")
public func setSocketBridge(_ env: JNIEnvPointer, _ this: jobject?, _ bridge: jobject?) {
    guard let bridge else { return env.throwNew("java/lang/NullPointerException", "bridge") }
    KotlinSockets.install(env, bridge)
}

@_cdecl("Java_ai_ishara_demo_core_IsharaCore_socketMessage")
public func socketMessage(_ env: JNIEnvPointer, _ this: jobject?, _ socketID: jlong, _ text: jstring?) {
    guard let text else { return }
    KotlinSockets.received(socketID, env.string(text))
}

/// `code` is the server's close code, or negative when the socket died without a close frame.
@_cdecl("Java_ai_ishara_demo_core_IsharaCore_socketClosed")
public func socketClosed(_ env: JNIEnvPointer, _ this: jobject?, _ socketID: jlong, _ code: jint) {
    KotlinSockets.closedByPeer(socketID, code: code < 0 ? nil : Int(code))
}
