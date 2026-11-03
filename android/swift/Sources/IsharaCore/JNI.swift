import CAndroidBridge

public typealias JNIEnvPointer = UnsafeMutablePointer<JNIEnv?>

nonisolated(unsafe) private var javaVM: UnsafeMutablePointer<JavaVM?>?

@_cdecl("JNI_OnLoad")
public func JNI_OnLoad(_ vm: UnsafeMutablePointer<JavaVM?>, _ reserved: UnsafeMutableRawPointer?) -> jint {
    javaVM = vm
    return JNI_VERSION_1_6
}

/// Runs `body` with a JNIEnv for the current thread, attaching it to the VM for the call if needed.
func withJNIEnv(_ body: (JNIEnvPointer) -> Void) {
    guard let vm = javaVM, let invoke = vm.pointee?.pointee else {
        log(.error, "JNI_OnLoad has not run")
        return
    }
    var existing: UnsafeMutableRawPointer?
    if invoke.GetEnv(vm, &existing, JNI_VERSION_1_6) == JNI_OK, let existing {
        body(existing.assumingMemoryBound(to: JNIEnv?.self))
        return
    }
    var attached: JNIEnvPointer?
    guard invoke.AttachCurrentThread(vm, &attached, nil) == JNI_OK, let attached else {
        log(.error, "AttachCurrentThread failed")
        return
    }
    defer { _ = invoke.DetachCurrentThread(vm) }
    body(attached)
}

extension UnsafeMutablePointer where Pointee == JNIEnv? {
    var jni: JNINativeInterface { pointee!.pointee }

    func string(_ value: jstring) -> String {
        let length = jni.GetStringLength(self, value)
        var units = [jchar](repeating: 0, count: Int(length))
        jni.GetStringRegion(self, value, 0, length, &units)
        return String(decoding: units, as: UTF16.self)
    }

    func newString(_ value: String) -> jstring? {
        let units = Array(value.utf16)
        let storage = units.isEmpty ? [jchar(0)] : units
        return storage.withUnsafeBufferPointer { jni.NewString(self, $0.baseAddress, jsize(units.count)) }
    }

    func throwNew(_ className: String, _ message: String) {
        guard let exceptionClass = jni.FindClass(self, className) else { return }
        _ = jni.ThrowNew(self, exceptionClass, message)
        jni.DeleteLocalRef(self, exceptionClass)
    }
}

enum LogLevel {
    case info, error

    var priority: Int32 {
        switch self {
        case .info: Int32(ANDROID_LOG_INFO.rawValue)
        case .error: Int32(ANDROID_LOG_ERROR.rawValue)
        }
    }
}

func log(_ level: LogLevel, _ message: String) {
    _ = __android_log_write(level.priority, "IsharaCore", message)
}
