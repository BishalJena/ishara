package ai.ishara.demo.recognition

import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlin.math.max
import kotlin.math.min

/**
 * Framing checklist plus the 2 s "hands at rest" calibration that teaches the start/stop
 * detector what rest looks like. The pipeline drives it from real frames ([pass],
 * [recordCalibration]); [runSimulatedChecks] ticks it on timers for replayed results.
 */
class GetReadyModel {
    enum class Check(val title: String) {
        FACE("Face visible"),
        BOTH_HANDS("Both hands visible"),
        LIGHT("Good light"),
    }

    data class State(val passedChecks: Set<Check> = emptySet(), val secondsAtRest: Double = 0.0) {
        val calibrationProgress: Double get() = min(1.0, secondsAtRest / CALIBRATION_SECONDS)
        val allChecksPassed: Boolean get() = passedChecks.size == Check.entries.size

        /** Small tolerance so summed timer steps can't fall a hair short of 2 s. */
        val isCalibrated: Boolean get() = secondsAtRest + 0.001 >= CALIBRATION_SECONDS
        val isReady: Boolean get() = allChecksPassed && isCalibrated
    }

    private val mutableState = MutableStateFlow(State())
    val state: StateFlow<State> = mutableState.asStateFlow()

    fun pass(check: Check) = mutableState.update { it.copy(passedChecks = it.passedChecks + check) }

    fun advanceCalibration(seconds: Double) = recordCalibration(state.value.secondsAtRest + seconds)

    /** Seconds of hands-at-rest recording collected so far. */
    fun recordCalibration(seconds: Double) = mutableState.update {
        if (!it.allChecksPassed) it else it.copy(secondsAtRest = min(CALIBRATION_SECONDS, max(0.0, seconds)))
    }

    /** The recording couldn't be used (for example the user left the frame); start over. */
    fun restartCalibration() = mutableState.update { it.copy(secondsAtRest = 0.0) }

    suspend fun runSimulatedChecks(timeScale: Double = 1.0) {
        for (check in Check.entries) {
            delay((600 * timeScale).toLong())
            pass(check)
        }
        val step = 0.1
        while (!state.value.isCalibrated) {
            delay((step * 1000 * timeScale).toLong())
            advanceCalibration(step)
        }
    }

    companion object {
        const val CALIBRATION_SECONDS = 2.0
    }
}
