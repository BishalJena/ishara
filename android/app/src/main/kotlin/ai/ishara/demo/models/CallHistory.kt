package ai.ishara.demo.models

import ai.ishara.demo.core.call.CallNotes
import ai.ishara.demo.core.call.CoreJson
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import java.io.File
import java.io.IOException
import java.nio.file.Files
import java.nio.file.StandardCopyOption

/**
 * Recent calls, kept on this phone only: one JSON file per call (`<id>.json`) in a folder,
 * written atomically. Without a folder the calls live in memory for this launch only
 * (UI tests, `IsharaCallHistory memory`). Use it from the main thread.
 */
class CallHistory(private val folder: File?) {
    /** Newest first. */
    var records: List<CallRecord> by mutableStateOf(emptyList())
        private set

    /** Saved calls that couldn't be read, or a call that couldn't be written. */
    var problem: String? by mutableStateOf(null)
        private set

    init {
        if (folder != null) load(folder)
    }

    /** Adds the call, or replaces the saved one with the same id. */
    fun save(record: CallRecord) {
        val others = records.filter { it.id != record.id }
        val index = others.indexOfFirst { it.date < record.date }.takeIf { it >= 0 } ?: others.size
        records = others.toMutableList().apply { add(index, record) }
        write(record)
    }

    /** The call's notes changed, for example Bolna's summary arrived after the call. */
    fun update(id: String, notes: CallNotes) {
        val record = records.firstOrNull { it.id == id } ?: return
        if (record.notes == notes) return
        save(record.copy(notes = notes))
    }

    fun delete(id: String) {
        records = records.filter { it.id != id }
        val file = folder?.let { file(id, it) } ?: return
        // Never written (a failed save) leaves nothing to remove.
        if (file.exists() && !file.delete()) problem = "A call couldn't be deleted from this phone."
    }

    private fun load(folder: File) {
        val files = folder.takeIf { it.isDirectory || it.mkdirs() }
            ?.listFiles { file -> file.extension == "json" }
        if (files == null) {
            problem = "Saved calls couldn't be read."
            return
        }
        var unreadable = 0
        val loaded = files.mapNotNull { file ->
            runCatching { CoreJson.decodeFromString(CallRecord.serializer(), file.readText()) }
                .onFailure { unreadable += 1 }
                .getOrNull()
        }
        records = loaded.sortedByDescending { it.date }
        if (unreadable > 0) {
            problem = if (unreadable == 1) "1 saved call couldn't be read." else "$unreadable saved calls couldn't be read."
        }
    }

    private fun write(record: CallRecord) {
        val folder = folder ?: return
        try {
            val temporary = File.createTempFile(record.id, ".tmp", folder)
            temporary.writeText(CoreJson.encodeToString(CallRecord.serializer(), record))
            Files.move(temporary.toPath(), file(record.id, folder).toPath(), StandardCopyOption.ATOMIC_MOVE)
        } catch (_: IOException) {
            problem = "The call with ${record.contactName} couldn't be saved on this phone."
        }
    }

    companion object {
        private fun file(id: String, folder: File) = File(folder, "$id.json")

        /** `CallHistory` in the app's files folder. */
        fun inFilesDir(filesDir: File) = CallHistory(File(filesDir, "CallHistory"))
    }
}
