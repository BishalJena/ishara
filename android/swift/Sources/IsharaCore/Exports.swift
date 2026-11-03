import CAndroidBridge

// JNI entry points for `ai.ishara.demo.core.IsharaCore` (a Kotlin object, so each call gets its instance).

@_cdecl("Java_ai_ishara_demo_core_IsharaCore_installMainQueuePump")
public func installMainQueuePump(_ env: JNIEnvPointer, _ this: jobject?) {
    do {
        try MainQueuePump.install()
    } catch {
        env.throwNew("java/lang/IllegalStateException", error.description)
    }
}

@_cdecl("Java_ai_ishara_demo_core_IsharaCore_setListener")
public func setListener(_ env: JNIEnvPointer, _ this: jobject?, _ listener: jobject?) {
    EventSink.set(env, listener)
}

@_cdecl("Java_ai_ishara_demo_core_IsharaCore_version")
public func version(_ env: JNIEnvPointer, _ this: jobject?) -> jstring? {
    env.newString(coreVersion)
}

@_cdecl("Java_ai_ishara_demo_core_IsharaCore_echoOnMain")
public func echoOnMain(_ env: JNIEnvPointer, _ this: jobject?, _ message: jstring?) {
    guard let message else { return env.throwNew("java/lang/NullPointerException", "message") }
    let echo = env.string(message)
    Task { @MainActor in
        EventSink.emit(encodeJSON(EchoEvent(echo: echo, onMainThread: gettid() == getpid())))
    }
}

@_cdecl("Java_ai_ishara_demo_core_IsharaCore_matchLogits")
public func matchLogits(
    _ env: JNIEnvPointer, _ this: jobject?, _ bundleJSON: jstring?, _ logitsJSON: jstring?, _ qualityJSON: jstring?
) -> jstring? {
    guard let bundleJSON, let logitsJSON, let qualityJSON else {
        env.throwNew("java/lang/NullPointerException", "matchLogits arguments")
        return nil
    }
    do {
        let output = try matchLogits(
            bundleJSON: env.string(bundleJSON), logitsJSON: env.string(logitsJSON), qualityJSON: env.string(qualityJSON))
        return env.newString(encodeJSON(output))
    } catch {
        env.throwNew("java/lang/IllegalArgumentException", String(describing: error))
        return nil
    }
}
