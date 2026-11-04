package ai.ishara.demo.recognition.core

import kotlinx.serialization.Serializable

/**
 * RecognitionCore's `LogitsMatcher` over a version-2 logits bundle (D8's open-set rule).
 * The constructor throws IllegalArgumentException for an invalid bundle. Close it when done.
 */
class NativeLogitsMatcher(bundleJson: String) : LogitsMatching, AutoCloseable {
    private var handle = RecognitionNative.createMatcher(bundleJson)
    private val info = RecognitionJson.decodeFromString<MatcherInfoWire>(RecognitionNative.matcherInfo(handle))

    /** The bundle's thresholds are probe defaults, not frozen on a labelled session. */
    val provisional: Boolean get() = info.provisional

    /** The model's class count the bundle expects (250 for the ASL Signs model). */
    val classCount: Int get() = info.classCount

    val vocabulary: List<String> get() = info.vocabulary

    override fun match(logits: FloatArray, quality: ClipQuality): LogitsMatch {
        check(handle != 0L) { "matcher closed" }
        val output = RecognitionJson.decodeFromString<MatchWire>(
            RecognitionNative.matchLogits(handle, logits, quality.poseFraction, quality.handFraction),
        )
        return output.result()
    }

    override fun close() {
        if (handle != 0L) RecognitionNative.freeMatcher(handle)
        handle = 0
    }
}

@Serializable
private data class MatcherInfoWire(val provisional: Boolean, val classCount: Int, val vocabulary: List<String>)

@Serializable
private data class MatchWire(
    val kind: String,
    val label: String? = null,
    val p: Double? = null,
    val margin: Double? = null,
    val reason: String? = null,
    val top: List<LogitsCandidate>,
) {
    fun result(): LogitsMatch = when (kind) {
        "chip" -> LogitsMatch.Chip(checkNotNull(label), checkNotNull(p), checkNotNull(margin), top)
        "pickOne" -> LogitsMatch.PickOne(checkNotNull(label), checkNotNull(p), checkNotNull(margin), top)
        "unsure" -> LogitsMatch.Unsure(reason.orEmpty(), top)
        else -> error("unknown match kind $kind")
    }
}
