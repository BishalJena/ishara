import CAndroidBridge
import Foundation
import RecognitionCore

// JNI entry points for `ai.ishara.demo.recognition.core.RecognitionNative`: RecognitionCore's
// start/stop detector, rest calibration, framing guard, clip quality and the open-set logits
// matcher, unchanged. Any thread may call them. Bad input (malformed JSON, an unknown handle,
// an invalid bundle) throws IllegalArgumentException; a null argument NullPointerException.

/// Runs `body` with the string arguments, mapping Swift errors to IllegalArgumentException.
private func call<Result>(
    _ env: JNIEnvPointer, _ name: String, _ arguments: [jstring?], fallback: Result, _ body: ([String]) throws -> Result
) -> Result {
    let present = arguments.compactMap { $0 }
    guard present.count == arguments.count else {
        env.throwNew("java/lang/NullPointerException", "\(name) arguments")
        return fallback
    }
    do {
        return try body(present.map(env.string))
    } catch {
        env.throwNew("java/lang/IllegalArgumentException", String(describing: error))
        return fallback
    }
}

/// The shared detector defaults as `{"calibration_s": 2.0, …}` (snake_case spec names).
@_cdecl("Java_ai_ishara_demo_recognition_core_RecognitionNative_defaultDetectorParams")
public func defaultDetectorParams(_ env: JNIEnvPointer, _ this: jobject?) -> jstring? {
    env.newString(DetectorParamsWire.encode(DetectorParams()))
}

/// `[DetectorFrame]` JSON plus params overrides → `{"restY"}` or `{"error"}`.
@_cdecl("Java_ai_ishara_demo_recognition_core_RecognitionNative_calibrate")
public func calibrate(_ env: JNIEnvPointer, _ this: jobject?, _ framesJSON: jstring?, _ paramsJSON: jstring?) -> jstring? {
    call(env, "calibrate", [framesJSON, paramsJSON], fallback: nil) { arguments in
        let frames = try JSONDecoder().decode([DetectorFrameWire].self, from: Data(arguments[0].utf8)).map { try $0.frame() }
        let params = try DetectorParamsWire.decode(arguments[1])
        let output: CalibrationOutput
        do throws(CalibrationError) {
            output = CalibrationOutput(restY: try SignDetector.calibrate(frames: frames, params: params))
        } catch {
            output = CalibrationOutput(error: error.rawValue)
        }
        return env.newString(encodeJSON(output))
    }
}

/// A new `SignDetector` at `restY`; free it with `freeDetector`.
@_cdecl("Java_ai_ishara_demo_recognition_core_RecognitionNative_createDetector")
public func createDetector(_ env: JNIEnvPointer, _ this: jobject?, _ restY: jdouble, _ paramsJSON: jstring?) -> jlong {
    call(env, "createDetector", [paramsJSON], fallback: 0) { arguments in
        detectors.add(SignDetector(restY: restY, params: try DetectorParamsWire.decode(arguments[0])))
    }
}

/// One frame (`wrists` flattened as x0, y0, x1, y1, …) → the detector's events as a JSON array.
@_cdecl("Java_ai_ishara_demo_recognition_core_RecognitionNative_detectorUpdate")
public func detectorUpdate(
    _ env: JNIEnvPointer, _ this: jobject?, _ handle: jlong, _ t: jdouble, _ body: jboolean, _ wrists: jdoubleArray?
) -> jstring? {
    guard let wrists else {
        env.throwNew("java/lang/NullPointerException", "wrists")
        return nil
    }
    let coordinates = env.doubles(wrists)
    guard coordinates.count.isMultiple(of: 2) else {
        env.throwNew("java/lang/IllegalArgumentException", "wrists must be x, y pairs")
        return nil
    }
    let points = stride(from: 0, to: coordinates.count, by: 2).map { NormalizedPoint(x: coordinates[$0], y: coordinates[$0 + 1]) }
    let frame = DetectorFrame(t: t, body: body != 0, wrists: points)
    guard let events = detectors.with(handle, { $0.update(frame) }) else {
        env.throwNew("java/lang/IllegalArgumentException", String(describing: UnknownHandle(kind: "detector", handle: handle)))
        return nil
    }
    return env.newString(encodeJSON(events.map(DetectorEventWire.init)))
}

@_cdecl("Java_ai_ishara_demo_recognition_core_RecognitionNative_freeDetector")
public func freeDetector(_ env: JNIEnvPointer, _ this: jobject?, _ handle: jlong) {
    detectors.remove(handle)
}

/// `[FramingFrame]` JSON and the calibrated rest line → `FramingGuard.handLeftFrame`.
@_cdecl("Java_ai_ishara_demo_recognition_core_RecognitionNative_handLeftFrame")
public func handLeftFrame(_ env: JNIEnvPointer, _ this: jobject?, _ framesJSON: jstring?, _ restY: jdouble) -> jboolean {
    call(env, "handLeftFrame", [framesJSON], fallback: 0) { arguments in
        let frames = try JSONDecoder().decode([FramingFrameWire].self, from: Data(arguments[0].utf8)).map(\.frame)
        return FramingGuard.handLeftFrame(frames, restY: restY) ? 1 : 0
    }
}

/// `[{"body", "handCount"}]` → `{"poseFraction", "handFraction"}` (`ClipQuality.from`).
@_cdecl("Java_ai_ishara_demo_recognition_core_RecognitionNative_clipQuality")
public func clipQuality(_ env: JNIEnvPointer, _ this: jobject?, _ framesJSON: jstring?) -> jstring? {
    call(env, "clipQuality", [framesJSON], fallback: nil) { arguments in
        let frames = try JSONDecoder().decode([QualityFrameWire].self, from: Data(arguments[0].utf8))
        let quality = ClipQuality.from(frames: frames.map { ClipQuality.Frame(body: $0.body, handCount: $0.handCount) })
        return env.newString(encodeJSON(QualityOutput(poseFraction: quality.poseFraction, handFraction: quality.handFraction)))
    }
}

/// A `LogitsMatcher` over a validated version-2 bundle; free it with `freeMatcher`.
@_cdecl("Java_ai_ishara_demo_recognition_core_RecognitionNative_createMatcher")
public func createMatcher(_ env: JNIEnvPointer, _ this: jobject?, _ bundleJSON: jstring?) -> jlong {
    call(env, "createMatcher", [bundleJSON], fallback: 0) { arguments in
        matchers.add(LogitsMatcher(try LogitsBundle.load(from: Data(arguments[0].utf8))))
    }
}

/// `{"provisional", "classCount", "vocabulary"}` of a matcher's bundle.
@_cdecl("Java_ai_ishara_demo_recognition_core_RecognitionNative_matcherInfo")
public func matcherInfo(_ env: JNIEnvPointer, _ this: jobject?, _ handle: jlong) -> jstring? {
    guard let bundle = matchers.with(handle, { $0.bundle }) else {
        env.throwNew("java/lang/IllegalArgumentException", String(describing: UnknownHandle(kind: "matcher", handle: handle)))
        return nil
    }
    return env.newString(encodeJSON(MatcherInfo(
        provisional: bundle.provisional, classCount: bundle.glosses.count, vocabulary: bundle.vocabulary)))
}

/// Raw logits plus the clip's tracking quality → the open-set decision, as `matchLogits` in Smoke.swift.
@_cdecl("Java_ai_ishara_demo_recognition_core_RecognitionNative_matchLogits")
public func matchLogitsWithMatcher(
    _ env: JNIEnvPointer, _ this: jobject?, _ handle: jlong, _ logits: jfloatArray?,
    _ poseFraction: jdouble, _ handFraction: jdouble
) -> jstring? {
    guard let logits else {
        env.throwNew("java/lang/NullPointerException", "logits")
        return nil
    }
    let values = env.floats(logits)
    let quality = ClipQuality(poseFraction: poseFraction, handFraction: handFraction)
    guard let result = matchers.with(handle, { $0.match(logits: values, quality: quality) }) else {
        env.throwNew("java/lang/IllegalArgumentException", String(describing: UnknownHandle(kind: "matcher", handle: handle)))
        return nil
    }
    return env.newString(encodeJSON(LogitsMatchOutput(result)))
}

@_cdecl("Java_ai_ishara_demo_recognition_core_RecognitionNative_freeMatcher")
public func freeMatcher(_ env: JNIEnvPointer, _ this: jobject?, _ handle: jlong) {
    matchers.remove(handle)
}
