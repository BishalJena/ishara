package ai.ishara.demo.core.call

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.withTimeoutOrNull
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit

const val TIMEOUT_MS = 5_000L

/** Runs [block] on the main thread (Swift's main actor) and waits for it; the main looper keeps running. */
fun <T> onMain(block: () -> T): T = runBlocking { withContext(Dispatchers.Main) { block() } }

/** Waits for a snapshot matching [predicate] and returns it. */
fun CallStore.awaitSnapshot(predicate: (CallSnapshot) -> Boolean): CallSnapshot = runBlocking {
    withTimeoutOrNull(TIMEOUT_MS) { snapshot.first(predicate) }
        ?: throw AssertionError("no matching snapshot within $TIMEOUT_MS ms; last: ${snapshot.value}")
}

fun <T> Flow<T>.awaitFirst(): T = runBlocking { withTimeout(TIMEOUT_MS) { first() } }

/** Collects a flow on a background thread into a queue, so a test can poll it. */
class Recorder<T>(flow: Flow<T>) : AutoCloseable {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private val items = LinkedBlockingQueue<T>()

    init {
        scope.launch { flow.collect { items.add(it) } }
    }

    fun next(): T = items.poll(TIMEOUT_MS, TimeUnit.MILLISECONDS) ?: throw AssertionError("nothing within $TIMEOUT_MS ms")

    /** Asserts nothing arrives within [millis]. */
    fun assertQuiet(millis: Long = 300) {
        val item = items.poll(millis, TimeUnit.MILLISECONDS)
        if (item != null) throw AssertionError("unexpected $item")
    }

    override fun close() = scope.cancel()
}
