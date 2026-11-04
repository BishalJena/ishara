package ai.ishara.demo.recognition.core

import ai.ishara.demo.core.IsharaCore

/**
 * RecognitionCore's JNI functions (`android/swift/Sources/IsharaCore/Recognition`). Any thread may
 * call them. Bad input throws IllegalArgumentException. Use them through [NativeRecognitionRules]
 * and [NativeLogitsMatcher].
 */
internal object RecognitionNative {
    init {
        // IsharaCore loads the library; it must be first loaded on the main thread (see IsharaCore).
        IsharaCore
    }

    /** The shared detector defaults, `{"calibration_s": 2.0, …}`. */
    external fun defaultDetectorParams(): String

    /** `[{"t", "body", "wrists": [[x, y]]}]` → `{"restY": Double}` or `{"error": "too_short" | "cant_see"}`. */
    external fun calibrate(framesJson: String, paramsJson: String): String

    external fun createDetector(restY: Double, paramsJson: String): Long

    /** [wrists] is x0, y0, x1, y1, …; returns `[{"status": …} | {"segment": {"start", "end", "reason"}}]`. */
    external fun detectorUpdate(handle: Long, t: Double, body: Boolean, wrists: DoubleArray): String

    external fun freeDetector(handle: Long)

    /** `[{"timestamp", "left": {"tracked", "wristX"?, "wristY"?}, "right": …}]`. */
    external fun handLeftFrame(framesJson: String, restY: Double): Boolean

    /** `[{"body", "handCount"}]` → `{"poseFraction", "handFraction"}`. */
    external fun clipQuality(framesJson: String): String

    /** Validates the version-2 logits bundle; IllegalArgumentException when it is invalid. */
    external fun createMatcher(bundleJson: String): Long

    /** `{"provisional", "classCount", "vocabulary"}`. */
    external fun matcherInfo(handle: Long): String

    /** → `{"kind": "chip" | "pickOne" | "unsure", "label"?, "p"?, "margin"?, "reason"?, "top": [{"gloss", "p"}]}`. */
    external fun matchLogits(handle: Long, logits: FloatArray, poseFraction: Double, handFraction: Double): String

    external fun freeMatcher(handle: Long)
}
