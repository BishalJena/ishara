package ai.ishara.demo

import ai.ishara.demo.core.IsharaCore
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.ln

/** Placeholder debug screen that exercises the Swift core; the real UI comes later. */
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val bundleJson = assets.open("asl-bundle.json").bufferedReader().use { it.readText() }
        setContent {
            MaterialTheme {
                CoreSmokeScreen(bundleJson)
            }
        }
    }
}

@Composable
private fun CoreSmokeScreen(bundleJson: String) {
    var echo by remember { mutableStateOf("waiting for the main actor…") }
    DisposableEffect(Unit) {
        IsharaCore.setListener { json -> echo = json }
        IsharaCore.echoOnMain("hello from Kotlin")
        onDispose { IsharaCore.setListener(null) }
    }
    val match = remember(bundleJson) {
        IsharaCore.matchLogits(
            bundleJson,
            sampleLogits(bundleJson, mapOf("tomorrow" to 0.72, "yourself" to 0.1)),
            """{"poseFraction":1.0,"handFraction":0.9}""",
        )
    }
    Scaffold { padding ->
        Column(
            modifier = Modifier.padding(padding).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text("Swift core smoke test", style = MaterialTheme.typography.titleLarge)
            LabeledValue("version()", IsharaCore.version())
            LabeledValue("echoOnMain()", echo)
            LabeledValue("matchLogits(tomorrow 0.72)", match)
        }
    }
}

@Composable
private fun LabeledValue(label: String, value: String) {
    Column {
        Text(label, style = MaterialTheme.typography.labelLarge)
        Text(value, style = MaterialTheme.typography.bodyMedium)
    }
}

/** Logits whose softmax gives the named glosses these probabilities; the rest share the remainder. */
private fun sampleLogits(bundleJson: String, mass: Map<String, Double>): String {
    val glosses = JSONObject(bundleJson).getJSONArray("glosses")
    val rest = (1.0 - mass.values.sum()) / (glosses.length() - mass.size)
    return JSONArray((0 until glosses.length()).map { ln(mass[glosses.getString(it)] ?: rest) }).toString()
}
