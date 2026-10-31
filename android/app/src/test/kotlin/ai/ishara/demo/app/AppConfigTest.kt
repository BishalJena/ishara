package ai.ishara.demo.app

import ai.ishara.demo.core.call.BackendConfig
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

/** Mirrors ios/IsharaTests/AppConfigTests.swift. */
class AppConfigTest {
    private fun problem(url: String?, token: String?): AppConfig.Problem? =
        runCatching { AppConfig.load(url, token) }.exceptionOrNull() as AppConfig.Problem?

    @Test
    fun readsBackendUrlAndToken() {
        val config = AppConfig.load(" https://ishara.example.test ", "secret\n")

        assertEquals(BackendConfig(baseUrl = "https://ishara.example.test", appToken = "secret"), config.backend)
    }

    @Test
    fun localHttpBackendIsAllowed() {
        assertEquals("http://10.0.2.2:8000", AppConfig.load("http://10.0.2.2:8000", "secret").backend.baseUrl)
    }

    @Test
    fun missingValuesAreReported() {
        assertEquals(AppConfig.Problem.MissingBackendUrl, problem(url = null, token = "secret"))
        assertEquals(AppConfig.Problem.MissingBackendUrl, problem(url = "  ", token = "secret"))
        assertEquals(AppConfig.Problem.MissingAppToken, problem(url = "https://ishara.example.test", token = null))
        assertEquals(AppConfig.Problem.MissingAppToken, problem(url = "https://ishara.example.test", token = " "))
    }

    @Test
    fun urlsWithoutHttpSchemeOrHostAreRejected() {
        assertEquals(AppConfig.Problem.InvalidBackendUrl("https:"), problem(url = "https:", token = "secret"))
        assertEquals(
            AppConfig.Problem.InvalidBackendUrl("ftp://ishara.example.test"),
            problem(url = "ftp://ishara.example.test", token = "secret"),
        )
        assertEquals(
            AppConfig.Problem.InvalidBackendUrl("ishara.example.test"),
            problem(url = "ishara.example.test", token = "secret"),
        )
    }

    @Test
    fun theTokenNeverShowsInLogs() {
        assertFalse(AppConfig.load("https://ishara.example.test", "secret").toString().contains("secret"))
    }
}
