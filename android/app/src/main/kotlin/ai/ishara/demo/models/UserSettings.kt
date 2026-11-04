package ai.ishara.demo.models

import android.content.SharedPreferences
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.core.content.edit

/**
 * What Ishara says about the user on every call, kept on this phone (iOS `@AppStorage`
 * keys `ishara.name` and `ishara.callback`). [callback] holds the 10 national digits.
 */
class UserSettings(private val store: Store) {
    /** Where the values live: SharedPreferences in the app, a map in tests. */
    interface Store {
        fun get(key: String): String?

        fun set(key: String, value: String)
    }

    var name: String by mutableStateOf(store.get(NAME).orEmpty())
        private set

    var callback: String by mutableStateOf(store.get(CALLBACK).orEmpty())
        private set

    fun updateName(value: String) {
        name = value
        store.set(NAME, value)
    }

    /** Keeps only the 10 national digits of whatever was typed or pasted. */
    fun updateCallback(raw: String) {
        val digits = if (raw.length > 10) Contact.indianDigits(raw) else raw.filter(Char::isDigit)
        callback = digits
        store.set(CALLBACK, digits)
    }

    /** UI tests start with a clean store and no way to type into Settings first. */
    fun presetNameIfEmpty(preset: String?) {
        if (name.isEmpty() && !preset.isNullOrBlank()) updateName(preset)
    }

    /** Said only when the receptionist asks how to reach the caller. */
    val callbackForCall: String? get() = if (callback.length == 10) Contact.display("+91$callback") else null

    class Preferences(private val preferences: SharedPreferences) : Store {
        override fun get(key: String): String? = preferences.getString(key, null)

        override fun set(key: String, value: String) {
            preferences.edit { putString(key, value) }
        }
    }

    class InMemory(private val values: MutableMap<String, String> = mutableMapOf()) : Store {
        override fun get(key: String): String? = values[key]

        override fun set(key: String, value: String) {
            values[key] = value
        }
    }

    companion object {
        const val NAME = "ishara.name"
        const val CALLBACK = "ishara.callback"
        const val PREFERENCES_FILE = "ishara"
    }
}
