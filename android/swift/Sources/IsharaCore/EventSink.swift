import CAndroidBridge
import Synchronization

/// The Kotlin listener (`CoreEventListener.onEvent(String)`) that receives JSON events from Swift.
enum EventSink {
    private struct Listener: @unchecked Sendable {
        let object: jobject
        let onEvent: jmethodID
    }

    private static let listener = Mutex<Listener?>(nil)

    static func set(_ env: JNIEnvPointer, _ object: jobject?) {
        var replacement: Listener?
        if let object {
            guard let objectClass = env.jni.GetObjectClass(env, object) else { return }
            defer { env.jni.DeleteLocalRef(env, objectClass) }
            guard let onEvent = env.jni.GetMethodID(env, objectClass, "onEvent", "(Ljava/lang/String;)V"),
                  let global = env.jni.NewGlobalRef(env, object)
            else { return }
            replacement = Listener(object: global, onEvent: onEvent)
        }
        let previous = listener.withLock { current in
            defer { current = replacement }
            return current
        }
        if let previous { env.jni.DeleteGlobalRef(env, previous.object) }
    }

    /// Delivers `json` to the listener on the calling thread; dropped when none is set.
    static func emit(_ json: String) {
        withJNIEnv { env in
            // Callers may be looper callbacks with no Java frame, so local refs need their own frame.
            guard env.jni.PushLocalFrame(env, 4) == JNI_OK else { return }
            defer { _ = env.jni.PopLocalFrame(env, nil) }
            let current = listener.withLock { current in
                current.flatMap { listener in
                    env.jni.NewLocalRef(env, listener.object).map { Listener(object: $0, onEvent: listener.onEvent) }
                }
            }
            guard let current else { return }
            var arguments = [jvalue(l: env.newString(json))]
            env.jni.CallVoidMethodA(env, current.object, current.onEvent, &arguments)
            if env.jni.ExceptionCheck(env) != 0 {
                log(.error, "CoreEventListener.onEvent threw")
                env.jni.ExceptionDescribe(env)
                env.jni.ExceptionClear(env)
            }
        }
    }
}
