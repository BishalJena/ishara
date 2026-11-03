package ai.ishara.demo.app

import ai.ishara.demo.BuildConfig
import ai.ishara.demo.core.call.BackendConfig
import java.net.URI
import java.net.URISyntaxException

/**
 * Backend settings baked into the app from the untracked `android/local.properties` keys
 * `ishara.backendUrl` and `ishara.appToken` (BuildConfig fields). Nothing real is committed;
 * without them the app can't place a live call.
 */
data class AppConfig(val backend: BackendConfig) {
    sealed class Problem(message: String) : Exception(message) {
        data object MissingBackendUrl : Problem("No backend URL. Set ishara.backendUrl in android/local.properties.")

        data class InvalidBackendUrl(val value: String) :
            Problem("The backend URL \u201C$value\u201D isn't an http(s) URL.")

        data object MissingAppToken : Problem("No app token. Set ishara.appToken in android/local.properties.")
    }

    companion object {
        /** Reads and checks the two values; blank counts as missing. */
        fun load(backendUrl: String?, appToken: String?): AppConfig {
            val rawUrl = backendUrl.orEmpty().trim()
            if (rawUrl.isEmpty()) throw Problem.MissingBackendUrl
            val uri = try {
                URI(rawUrl)
            } catch (_: URISyntaxException) {
                throw Problem.InvalidBackendUrl(rawUrl)
            }
            if (uri.scheme?.lowercase() !in setOf("http", "https") || uri.host == null) {
                throw Problem.InvalidBackendUrl(rawUrl)
            }
            val token = appToken.orEmpty().trim()
            if (token.isEmpty()) throw Problem.MissingAppToken
            return AppConfig(BackendConfig(baseUrl = rawUrl, appToken = token))
        }

        /** This build's configuration, or why a live call can't be placed. */
        fun fromBuildConfig(): Result<AppConfig> = runCatching {
            load(BuildConfig.ISHARA_BACKEND_URL, BuildConfig.ISHARA_APP_TOKEN)
        }
    }
}
