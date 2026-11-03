package ai.ishara.demo.core

import android.util.Log
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.CopyOnWriteArrayList

/**
 * The one [IsharaCore] listener. Every Swift event is a JSON object with a `type`; each
 * feature subscribes to the types it handles. Handlers run on the emitting thread
 * (the main thread for call events).
 */
object CoreEvents {
    private val handlers = ConcurrentHashMap<String, CopyOnWriteArrayList<(JsonObject) -> Unit>>()

    /** Installs the listener. Call once the main-queue pump is installed. */
    fun install() {
        IsharaCore.setListener(::dispatch)
    }

    fun subscribe(type: String, handler: (JsonObject) -> Unit): AutoCloseable {
        val list = handlers.computeIfAbsent(type) { CopyOnWriteArrayList() }
        list.add(handler)
        return AutoCloseable { list.remove(handler) }
    }

    private fun dispatch(json: String) {
        val event = Json.parseToJsonElement(json).jsonObject
        val type = event["type"]?.jsonPrimitive?.content
        val subscribers = type?.let(handlers::get)
        if (subscribers.isNullOrEmpty()) {
            Log.w("CoreEvents", "no handler for event type $type")
            return
        }
        subscribers.forEach { it(event) }
    }
}
